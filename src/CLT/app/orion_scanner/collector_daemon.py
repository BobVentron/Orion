"""
Orion Collector — daemon orchestrateur.

Architecture
------------
Un thread principal (orchestrateur) tourne en boucle toutes les POLL_INTERVAL
secondes. À chaque passe il lit scan_networks, identifie les réseaux éligibles
et soumet chaque scan dans un ThreadPoolExecutor.

                ┌─────────────────────────────────────┐
                │  Orchestrateur  (thread principal)  │
                │  boucle toutes les POLL_INTERVAL s  │
                └────────────┬────────────────────────┘
                             │ soumet si éligible + pas déjà en cours
                    ┌────────▼─────────────────────┐
                    │  ThreadPoolExecutor           │
                    │  MAX_CONCURRENT_SCANS workers │
                    │  ┌──────────┐ ┌──────────┐   │
                    │  │ scan #1  │ │ scan #2  │   │
                    │  └──────────┘ └──────────┘   │
                    └──────────────────────────────┘

Règles de scheduling
--------------------
- Un réseau avec last_scan_status = 'running' est toujours skippé
- Un réseau est éligible si next_scan_at IS NULL ou next_scan_at <= NOW()
- Deux scans sur le même network_id ne peuvent pas tourner en même temps
  (protection par _active_scans set, accès protégé par un Lock)
- MAX_CONCURRENT_SCANS limite le nombre de scans réseau simultanés

Variables d'environnement
--------------------------
    DATABASE_URL          URL PostgreSQL (obligatoire)
    POLL_INTERVAL         Secondes entre deux passes de l'orchestrateur (défaut: 5)
    MAX_CONCURRENT_SCANS  Scans réseau en parallèle max (défaut: 3)
    LOG_LEVEL             DEBUG / INFO / WARNING (défaut: INFO)
"""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from orion_scanner.db.engine import check_connection, get_engine
from orion_scanner.db.schema import AuthProfile, AuthSnmp, Device, Interface, DeviceMonitoringTask, MonitoringProfile, ScanNetwork
from orion_scanner.db.writer import (
    write_scan_results,
    write_device_metrics, write_interface_metrics,
    write_redundancy, write_etherchannel, write_trunks,
    write_mac_table, write_interface_statuses,
    write_arp, write_routing, write_stp,
)
from orion_scanner.models import (
    ScanTarget,
    SnmpV1V2Credentials,
    SnmpV3Credentials,
    SnmpVersion,
    V3AuthProto,
    V3Level,
    V3PrivProto,
)
from orion_scanner.snmp.collector import scan_target
from orion_scanner.utils.logger import get_logger

logger = get_logger("orion_collector")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

POLL_INTERVAL:        int = int(os.environ.get("POLL_INTERVAL",        "5"))
MAX_CONCURRENT_SCANS: int = int(os.environ.get("MAX_CONCURRENT_SCANS", "3"))

# ---------------------------------------------------------------------------
# État global des scans en cours
# Protégé par _active_lock — accès depuis l'orchestrateur ET les threads worker.
# ---------------------------------------------------------------------------

_active_scans: set[int] = set()        # network_id des scans en cours (workers subnet)
_active_monitoring: set[tuple] = set()   # (device_id_str, profile_id) des monitoring tasks actives
_active_lock  = threading.Lock()

# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------

_running = True


def _handle_signal(signum: int, frame: object) -> None:  # noqa: ARG001
    global _running
    logger.info("Signal %d reçu — arrêt en cours (scans en cours terminés avant)…", signum)
    _running = False


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT,  _handle_signal)


# ---------------------------------------------------------------------------
# Credentials builder
# ---------------------------------------------------------------------------

def _build_credentials(
    network: ScanNetwork,
) -> SnmpV1V2Credentials | SnmpV3Credentials | None:
    """Construit les credentials SNMP depuis auth_profile → auth_snmp."""
    auth_profile = network.auth_profile
    if auth_profile is None:
        logger.warning("Réseau %s — auth_profile introuvable (id=%d)",
                       network.subnet, network.auth_profile_id)
        return None

    snmp = auth_profile.snmp
    if snmp is None:
        logger.warning("Réseau %s — auth_profile '%s' sans config SNMP.",
                       network.subnet, auth_profile.name)
        return None

    version = snmp.version.lower().strip()

    if version in ("v1", "v2c"):
        if not snmp.community:
            logger.warning("Réseau %s — SNMP %s sans community.", network.subnet, version)
            return None
        creds = SnmpV1V2Credentials(
            version=SnmpVersion(version),
            community=snmp.community,
            port=snmp.port,
        )
        creds._auth_profile_id = network.auth_profile_id
        return creds

    if version == "v3":
        if not snmp.v3_user:
            logger.warning("Réseau %s — SNMPv3 sans username.", network.subnet)
            return None
        try:
            level = V3Level(snmp.v3_level or "noAuthNoPriv")
        except ValueError:
            logger.warning("Réseau %s — niveau SNMPv3 inconnu : '%s'.",
                           network.subnet, snmp.v3_level)
            return None

        auth_proto = priv_proto = None
        if level in (V3Level.AUTH_NO_PRIV, V3Level.AUTH_PRIV):
            try:
                auth_proto = V3AuthProto(snmp.v3_auth_proto or "SHA")
            except ValueError:
                auth_proto = V3AuthProto.SHA
        if level == V3Level.AUTH_PRIV:
            try:
                priv_proto = V3PrivProto(snmp.v3_priv_proto or "AES")
            except ValueError:
                priv_proto = V3PrivProto.AES

        creds = SnmpV3Credentials(
            username=snmp.v3_user,
            level=level,
            auth_proto=auth_proto,
            auth_pass=snmp.v3_auth_pass,
            priv_proto=priv_proto,
            priv_pass=snmp.v3_priv_pass,
            port=snmp.port,
        )
        creds._auth_profile_id = network.auth_profile_id
        return creds

    logger.warning("Réseau %s — version SNMP non supportée : '%s'.",
                   network.subnet, snmp.version)
    return None


# ---------------------------------------------------------------------------
# Eligibility check
# ---------------------------------------------------------------------------

def _is_eligible(network: ScanNetwork) -> bool:
    """
    Retourne True si le réseau doit être soumis au scanner.

    Ordre de vérification :
    1. running en base     → skip (le thread précédent n'a pas encore fini)
    2. déjà dans _active_scans → skip (thread en cours pour ce network_id)
    3. scan_profile désactivé  → skip
    4. next_scan_at IS NULL    → éligible (premier scan)
    5. next_scan_at <= NOW()   → éligible (heure atteinte)
    6. sinon                   → trop tôt, skip
    """
    if network.last_scan_status == "running":
        logger.debug("Réseau %s — déjà running en base, ignoré.", network.subnet)
        return False

    with _active_lock:
        if network.id in _active_scans:
            logger.debug("Réseau %s — thread actif (id=%d), ignoré.", network.subnet, network.id)
            return False

    scan_profile = network.scan_profile
    if scan_profile is not None and not scan_profile.is_enabled:
        logger.debug("Réseau %s — scan_profile désactivé.", network.subnet)
        return False

    if network.next_scan_at is None:
        return True

    now     = datetime.now(tz=timezone.utc)
    next_at = network.next_scan_at
    if hasattr(next_at, "tzinfo") and next_at.tzinfo is None:
        next_at = next_at.replace(tzinfo=timezone.utc)

    if next_at <= now:
        return True

    remaining = int((next_at - now).total_seconds() / 3600)
    logger.debug("Réseau %s — prochain scan dans ~%dh (%s).",
                 network.subnet, remaining, next_at.strftime("%Y-%m-%d %H:%M UTC"))
    return False


# ---------------------------------------------------------------------------
# Helpers — sélection du meilleur profil pour un device connu
# ---------------------------------------------------------------------------

# Force relative des versions SNMP : v3 > v2c > v1
_SNMP_VERSION_STRENGTH: dict[str, int] = {
    "v3":  3,
    "v2c": 2,
    "v1":  1,
}


def _profile_strength(auth_profile: AuthProfile) -> int:
    """Retourne un score de force pour un profil d'auth (plus élevé = plus fort)."""
    if auth_profile.snmp is None:
        return 0
    return _SNMP_VERSION_STRENGTH.get(auth_profile.snmp.version.lower().strip(), 0)


def _build_credentials_from_profile(
    auth_profile: AuthProfile,
    network: ScanNetwork,
) -> SnmpV1V2Credentials | SnmpV3Credentials | None:
    """
    Construit les credentials depuis un auth_profile explicite.
    Identique à _build_credentials mais prend un AuthProfile directement.
    """
    snmp = auth_profile.snmp
    if snmp is None:
        return None

    version = snmp.version.lower().strip()

    if version in ("v1", "v2c"):
        if not snmp.community:
            return None
        creds = SnmpV1V2Credentials(
            version=SnmpVersion(version),
            community=snmp.community,
            port=snmp.port,
        )
        creds._auth_profile_id = auth_profile.id
        return creds

    if version == "v3":
        if not snmp.v3_user:
            return None
        try:
            level = V3Level(snmp.v3_level or "noAuthNoPriv")
        except ValueError:
            return None

        auth_proto = priv_proto = None
        if level in (V3Level.AUTH_NO_PRIV, V3Level.AUTH_PRIV):
            try:
                auth_proto = V3AuthProto(snmp.v3_auth_proto or "SHA")
            except ValueError:
                auth_proto = V3AuthProto.SHA
        if level == V3Level.AUTH_PRIV:
            try:
                priv_proto = V3PrivProto(snmp.v3_priv_proto or "AES")
            except ValueError:
                priv_proto = V3PrivProto.AES

        creds = SnmpV3Credentials(
            username=snmp.v3_user,
            level=level,
            auth_proto=auth_proto,
            auth_pass=snmp.v3_auth_pass,
            priv_proto=priv_proto,
            priv_pass=snmp.v3_priv_pass,
            port=snmp.port,
        )
        creds._auth_profile_id = auth_profile.id
        return creds

    return None


def _resolve_device_credentials(
    session: Session,
    ip: str,
    scan_network: ScanNetwork,
) -> SnmpV1V2Credentials | SnmpV3Credentials | None:
    """
    Détermine les credentials à utiliser pour un device spécifique.

    Priorité :
    1. Si le device existe déjà en base avec un auth_profile_id → utilise ce profil
    2. Sinon → utilise le profil du scan réseau (scan_network.auth_profile)

    Le profil stocké sur le device est celui qui a fonctionné lors du scan
    initial. On ne le remet pas en question sauf si le scan échoue (géré
    ailleurs).

    Args:
        session:      Session SQLAlchemy active.
        ip:           IP de l'équipement à scanner.
        scan_network: Entrée scan_networks en cours de traitement.

    Returns:
        Credentials prêts à l'emploi, ou None si impossible à construire.
    """
    from sqlalchemy import select as sa_select
    from orion_scanner.db.schema import IpAddress, IpInterfaceMap, Interface

    # Chercher si ce device existe déjà via son IP de management
    device = None
    try:
        ip_row = session.scalar(
            sa_select(IpAddress).where(IpAddress.address == ip)
        )
        if ip_row:
            map_row = session.scalar(
                sa_select(IpInterfaceMap)
                .where(IpInterfaceMap.ip_address_id == ip_row.id)
                .where(IpInterfaceMap.is_primary == True)  # noqa: E712
            )
            if map_row:
                iface = session.get(Interface, map_row.interface_id)
                if iface:
                    device = session.get(Device, iface.device_id)
    except Exception as exc:
        logger.debug("Impossible de chercher le device pour %s : %s", ip, exc)

    if device and device.auth_profile_id:
        profile = session.get(AuthProfile, device.auth_profile_id)
        if profile:
            creds = _build_credentials_from_profile(profile, scan_network)
            if creds:
                logger.debug(
                    "Device %s — utilise profil mémorisé '%s' (id=%d)",
                    ip, profile.name, profile.id,
                )
                return creds

    # Fallback : profil du scan réseau
    return _build_credentials(scan_network)


# ---------------------------------------------------------------------------
# Worker function (s'exécute dans un thread dédié)
# ---------------------------------------------------------------------------

def _worker(network_id: int, engine) -> None:
    """
    Exécute le scan complet d'un réseau dans un thread indépendant.

    Chaque worker possède sa propre session SQLAlchemy — aucun état partagé
    avec l'orchestrateur ni avec les autres workers.

    En cas d'exception non catchée, l'erreur est loguée, le réseau est
    marqué 'failed' en base et le thread se termine proprement.
    """
    subnet = f"network_id={network_id}"  # fallback avant de lire la DB

    # Enregistrer dans _active_scans
    with _active_lock:
        _active_scans.add(network_id)

    try:
        with Session(engine) as session:
            network = session.get(ScanNetwork, network_id)
            if network is None:
                logger.error("Worker — réseau id=%d introuvable en base.", network_id)
                return

            subnet = str(network.subnet)
            scan_profile = network.scan_profile

            # Paramètres techniques
            timeout_s   = max((scan_profile.timeout_ms // 1000) if scan_profile else 2, 1)
            retries     = scan_profile.retry_count            if scan_profile else 1
            max_workers = scan_profile.concurrency_threads    if scan_profile else 20

            # Exclusions IP
            exclude_ips: list[str] = []
            raw_excl = network.exclude_ips
            if raw_excl:
                if isinstance(raw_excl, list):
                    exclude_ips = [str(ip) for ip in raw_excl if ip]
                elif isinstance(raw_excl, str):
                    try:
                        parsed = json.loads(raw_excl)
                        exclude_ips = [str(ip) for ip in parsed if ip] if isinstance(parsed, list) else []
                    except (json.JSONDecodeError, TypeError):
                        logger.warning("Réseau %s — exclude_ips invalide, ignoré.", subnet)
            if exclude_ips:
                logger.debug("Réseau %s — %d IP(s) exclue(s).", subnet, len(exclude_ips))

            # Marquer running
            started_at = datetime.now(tz=timezone.utc)
            network.last_scan_status = "running"
            network.last_scan_at     = started_at
            network.last_error       = None
            try:
                session.flush()
                session.commit()
            except Exception as exc:
                logger.error("Impossible de marquer %s running : %s", subnet, exc)
                session.rollback()
                return

            logger.info("▶ Scan démarré  : %s  (timeout=%ds threads=%d)",
                        subnet, timeout_s, max_workers)

            # Construire credentials
            credentials = _build_credentials(network)
            if credentials is None:
                _mark_failed_worker(session, network, "Credentials SNMP manquants ou invalides.")
                return

            target = ScanTarget(
                subnet=subnet,
                credentials=credentials,
                exclude_ips=exclude_ips,
                timeout=timeout_s,
                retries=retries,
            )

            # Écriture progressive : chaque device est persisté dès qu'il répond
            written      = 0
            write_errors = 0

            # Collecter tous les profils disponibles pour ce subnet
            # (plusieurs scan_networks peuvent couvrir le même subnet avec des profils différents)
            from sqlalchemy import select as sa_select
            subnet_profiles: list[AuthProfile] = []
            try:
                subnet_scan_rows = session.scalars(
                    sa_select(ScanNetwork).where(ScanNetwork.subnet == network.subnet)
                ).all()
                for row in subnet_scan_rows:
                    if row.auth_profile:
                        subnet_profiles.append(row.auth_profile)
                # Trier par force décroissante : v3 > v2c > v1
                subnet_profiles.sort(key=_profile_strength, reverse=True)
                logger.debug(
                    "Réseau %s — %d profil(s) disponible(s) : %s",
                    subnet,
                    len(subnet_profiles),
                    [p.name for p in subnet_profiles],
                )
            except Exception as exc:
                logger.warning("Impossible de charger les profils pour %s : %s", subnet, exc)

            def _on_host_found(ip: str, result) -> None:
                """
                Callback appelé dès qu'un host répond au SNMP.

                Si le device n'a pas encore de profil mémorisé, on sélectionne
                le meilleur parmi ceux disponibles pour ce subnet (v3 > v2c > v1)
                et on l'inscrit dans result.credentials_used._auth_profile_id
                pour que le writer le stocke sur devices.auth_profile_id.
                """
                nonlocal written, write_errors
                if not result.is_successful:
                    return

                # Sélectionner le meilleur profil si le device n'en a pas encore
                # On laisse les credentials de result tels quels — ils contiennent
                # déjà le profil qui a réussi le probe SNMP.
                # On enrichit avec le profil "le plus fort" disponible pour ce subnet
                # afin de stocker le meilleur profil sur le device pour les scans futurs.
                if subnet_profiles:
                    best_profile = subnet_profiles[0]  # déjà trié par force
                    current_strength = _SNMP_VERSION_STRENGTH.get(
                        (getattr(result.credentials_used, 'version', None) or
                         SnmpVersion.V2C).value.lower(), 2
                    )
                    best_strength = _profile_strength(best_profile)
                    if best_strength > current_strength:
                        # Un profil plus fort existe — l'indiquer pour stockage sur le device
                        result.credentials_used._auth_profile_id = best_profile.id
                        logger.debug(
                            "Device %s — profil upgrade vers '%s' (force %d→%d)",
                            ip, best_profile.name, current_strength, best_strength,
                        )
                    elif not hasattr(result.credentials_used, '_auth_profile_id'):
                        result.credentials_used._auth_profile_id = network.auth_profile_id

                try:
                    count = write_scan_results(session, [result])
                    written += count
                except Exception as exc:
                    write_errors += 1
                    logger.error("Erreur écriture %s : %s", ip, exc)

            # Lancer le scan SNMP
            try:
                scan_target(target, max_workers=max_workers, progress_callback=_on_host_found)
            except Exception as exc:
                logger.error("Erreur scan %s : %s", subnet, exc, exc_info=True)
                _mark_failed_worker(session, network, str(exc))
                return

            # Marquer completed
            duration_s = int((datetime.now(tz=timezone.utc) - started_at).total_seconds())
            interval_s = network.interval_seconds if network.interval_seconds else 0
            network.last_scan_status   = "completed"
            network.last_scan_duration = duration_s
            network.last_hosts_found   = written
            network.last_error         = None
            network.next_scan_at       = (
                datetime.now(tz=timezone.utc) + timedelta(seconds=interval_s)
                if interval_s > 0 else None
            )
            session.flush()
            session.commit()

            next_info = (
                network.next_scan_at.strftime("%Y-%m-%d %H:%M UTC")
                if network.next_scan_at else "pas de reschedule"
            )
            if write_errors:
                logger.warning(
                    "■ Scan terminé  : %s — %d device(s) en %ds (%d erreur(s) écriture) | prochain: %s",
                    subnet, written, duration_s, write_errors, next_info,
                )
            else:
                logger.info(
                    "■ Scan terminé  : %s — %d device(s) en %ds | prochain: %s",
                    subnet, written, duration_s, next_info,
                )

    except Exception as exc:
        # Filet de sécurité — ne doit jamais arriver mais garantit que le thread
        # ne meurt pas silencieusement
        logger.error("ERREUR FATALE worker %s : %s", subnet, exc, exc_info=True)
        traceback.print_exc()
        # Tentative de marquer failed avec une session fraîche
        try:
            with Session(engine) as session:
                network = session.get(ScanNetwork, network_id)
                if network:
                    _mark_failed_worker(session, network, f"Exception fatale: {exc}")
        except Exception:
            pass

    finally:
        # Toujours retirer de _active_scans, même si exception
        with _active_lock:
            _active_scans.discard(network_id)
        logger.debug("Worker terminé pour network_id=%d (%s).", network_id, subnet)



# ---------------------------------------------------------------------------
# Worker monitoring — checks récurrents sur devices connus
# ---------------------------------------------------------------------------

def _worker_monitoring(task_key: tuple[str, int], engine) -> None:
    """
    Worker de monitoring récurrent.

    Exécute un check sur UN device pour UN profil donné.
    task_key = (device_id_str, profile_id)

    Types gérés :
      ICMP_Ping     → ping + mise à jour device_status
      SNMP_Metrics  → CPU/RAM/temp + compteurs interfaces
      LLDP_Topology → voisins LLDP/CDP + network_links
      SNMP_Full     → Metrics + Trunks + EtherChannel + HSRP + Topology
    """
    from sqlalchemy import select as sa_select
    from orion_scanner.snmp.client import SnmpClient
    from orion_scanner.snmp.check_interfaces import check_interfaces
    from orion_scanner.snmp.check_mac_table import check_mac_table
    from orion_scanner.snmp.check_metrics import collect_metrics
    from orion_scanner.snmp.check_etherchannel import check_etherchannel
    from orion_scanner.snmp.check_trunks import check_trunks
    from orion_scanner.snmp.check_hsrp import check_hsrp_vrrp
    from orion_scanner.snmp.topology import collect_topology
    from orion_scanner.snmp.check_topology import process_lldp_neighbors
    from orion_scanner.db.schema import DeviceMonitoringTask, MonitoringProfile, Interface, Vlan
    import uuid as _uuid

    device_id_str, profile_id = task_key
    label = f"monitoring device={device_id_str[:8]}… profile={profile_id}"

    try:
        device_uuid = _uuid.UUID(device_id_str)
    except ValueError:
        logger.error("Worker monitoring — UUID invalide : %s", device_id_str)
        return

    try:
        with Session(engine) as session:
            task = session.get(DeviceMonitoringTask, (device_uuid, profile_id))
            if task is None:
                logger.error("Task introuvable : %s", label)
                return

            profile = task.profile
            if profile is None or not profile.is_enabled or not task.is_enabled:
                return

            device = session.get(Device, device_uuid)
            if device is None:
                logger.error("Device introuvable : %s", device_id_str)
                return

            if device.auth_profile_id is None:
                logger.debug("Device %s sans auth_profile, monitoring ignoré.", device.hostname)
                return

            auth_profile = session.get(AuthProfile, device.auth_profile_id)
            if auth_profile is None:
                return

            # Marquer running
            task.last_run_status = "running"
            session.flush()
            session.commit()

            timeout_s = max(profile.timeout_ms // 1000, 1)

            # Résoudre l'IP de management
            from orion_scanner.db.schema import IpAddress, IpInterfaceMap
            mgmt_ip: str | None = None
            for iface in session.scalars(
                sa_select(Interface).where(Interface.device_id == device_uuid)
            ).all():
                map_row = session.scalar(
                    sa_select(IpInterfaceMap)
                    .where(IpInterfaceMap.interface_id == iface.id)
                    .where(IpInterfaceMap.is_primary == True)  # noqa: E712
                )
                if map_row:
                    ip_row = session.get(IpAddress, map_row.ip_address_id)
                    if ip_row:
                        mgmt_ip = str(ip_row.address).split("/")[0]
                        break

            if mgmt_ip is None:
                _finish_task(session, task, profile, "failed", "IP de management introuvable")
                return

            # Construire credentials
            scan_net_stub = type("_Stub", (), {"auth_profile_id": device.auth_profile_id})()
            creds = _build_credentials_from_profile(auth_profile, scan_net_stub)
            if creds is None:
                _finish_task(session, task, profile, "failed", "Credentials invalides")
                return

            scan_type = profile.scan_type
            logger.debug("▷ %s | %s | ip=%s", scan_type, device.hostname, mgmt_ip)

            # Mapping ifIndex → db_id (commun à tous les types)
            interfaces = session.scalars(
                sa_select(Interface).where(Interface.device_id == device_uuid)
            ).all()
            if_index_to_db_id = {ifc.if_index: ifc.id for ifc in interfaces}

            # ── ICMP_Ping ────────────────────────────────────────────────
            if scan_type == "ICMP_Ping":
                import subprocess, time
                t0 = time.monotonic()
                try:
                    r = subprocess.run(
                        ["ping", "-c", "3", "-W", "1", mgmt_ip],
                        capture_output=True, timeout=10,
                    )
                    rtt_ms = (time.monotonic() - t0) * 1000 / 3
                    loss   = 100 if r.returncode != 0 else 0
                    snmp_s = "Reachable" if r.returncode == 0 else "Unreachable"
                    icmp_s = snmp_s
                except Exception:
                    rtt_ms, loss, snmp_s, icmp_s = None, 100, "Unreachable", "Unreachable"

                from sqlalchemy.dialects.postgresql import insert as pg_insert
                from orion_scanner.db.schema import DeviceStatus, DeviceMetricsHistory
                stmt = (
                    pg_insert(DeviceStatus)
                    .values(device_id=device_uuid, last_poll=datetime.now(tz=timezone.utc),
                            icmp_status=icmp_s, snmp_status=snmp_s)
                    .on_conflict_do_update(
                        constraint="device_status_pkey",
                        set_={"last_poll": datetime.now(tz=timezone.utc),
                              "icmp_status": icmp_s, "snmp_status": snmp_s},
                    )
                )
                session.execute(stmt)
                if rtt_ms is not None:
                    from orion_scanner.snmp.check_metrics import DeviceMetricsResult
                    write_device_metrics(session, device_uuid,
                                         DeviceMetricsResult(), rtt_ms, loss)
                session.commit()
                _finish_task(session, task, profile, "ok")
                logger.debug("ICMP %s : %s rtt=%.1fms loss=%d%%",
                             device.hostname, icmp_s, rtt_ms or 0, loss)
                return

            # Probe SNMP pour les types suivants
            client = SnmpClient(ip=mgmt_ip, credentials=creds,
                                timeout=timeout_s, retries=profile.retry_count)
            if not client.probe():
                logger.debug("Probe KO : %s (%s)", device.hostname, mgmt_ip)
                _finish_task(session, task, profile, "failed", "SNMP probe failed")
                return

            # ── SNMP_Metrics ─────────────────────────────────────────────
            if scan_type in ("SNMP_Metrics", "SNMP_Full"):
                try:
                    with session.begin_nested():
                        m = collect_metrics(client)
                        write_device_metrics(session, device_uuid, m.device)
                        write_interface_metrics(session, m.interfaces, if_index_to_db_id)
                        iface_statuses = check_interfaces(client)
                        write_interface_statuses(session, device_uuid,
                                                 iface_statuses, if_index_to_db_id)
                except Exception as exc:
                    logger.warning("SNMP_Metrics %s : %s", device.hostname, exc)

            # ── LLDP_Topology ou SNMP_Full ───────────────────────────────
            if scan_type in ("LLDP_Topology", "SNMP_Full"):
                try:
                    with session.begin_nested():
                        neighbors = collect_topology(client)
                        links, unresolved = process_lldp_neighbors(
                            session, device, neighbors, if_index_to_db_id
                        )
                    logger.debug("Topology %s : %d liens, %d non-résolus.",
                                 device.hostname, links, unresolved)
                except Exception as exc:
                    logger.warning("LLDP %s : %s", device.hostname, exc)

            # ── SNMP_Full uniquement ─────────────────────────────────────
            if scan_type == "SNMP_Full":
                # EtherChannel — savepoint
                try:
                    with session.begin_nested():
                        lag_entries = check_etherchannel(client)
                        write_etherchannel(session, lag_entries, if_index_to_db_id)
                except Exception as exc:
                    logger.warning("EtherChannel %s : %s", device.hostname, exc)

                # Trunks + memberships VLAN — savepoint
                try:
                    with session.begin_nested():
                        trunk_result = check_trunks(client)
                        vlan_tag_to_db_id = {
                            v.vlan_tag: v.id
                            for v in session.scalars(
                                sa_select(Vlan).where(Vlan.device_id == device_uuid)
                            ).all()
                        }
                        t_cnt, v_cnt = write_trunks(
                            session, device_uuid,
                            trunk_result.trunks, trunk_result.vlans,
                            if_index_to_db_id, vlan_tag_to_db_id,
                        )
                    logger.debug("Trunks %s : %d trunks, %d memberships.",
                                 device.hostname, t_cnt, v_cnt)
                except Exception as exc:
                    logger.warning("Trunks %s : %s", device.hostname, exc)

                # HSRP / VRRP — savepoint
                try:
                    with session.begin_nested():
                        hsrp_entries = check_hsrp_vrrp(client)
                        write_redundancy(session, device_uuid,
                                         hsrp_entries, if_index_to_db_id)
                except Exception as exc:
                    logger.warning("HSRP/VRRP %s : %s", device.hostname, exc)

                # FDB MAC table — savepoint
                try:
                    with session.begin_nested():
                        mac_entries = check_mac_table(client)
                        write_mac_table(session, mac_entries, if_index_to_db_id)
                except Exception as exc:
                    logger.warning("MAC table %s : %s", device.hostname, exc)

                # Table ARP — savepoint pour isolation (rollback ne détruit pas le reste)
                try:
                    from orion_scanner.snmp.check_arp import check_arp
                    with session.begin_nested():
                        arp_entries = check_arp(client)
                        write_arp(session, device_uuid, arp_entries, if_index_to_db_id)
                except Exception as exc:
                    logger.warning("ARP %s : %s", mgmt_ip, exc)

                # Table de routage — savepoint
                try:
                    from orion_scanner.snmp.check_routing import check_routing
                    with session.begin_nested():
                        routes = check_routing(client)
                        write_routing(session, device_uuid, routes, if_index_to_db_id)
                except Exception as exc:
                    logger.warning("Routing %s : %s", mgmt_ip, exc)

                # STP — savepoint
                try:
                    from orion_scanner.snmp.check_stp import check_stp
                    with session.begin_nested():
                        stp_result = check_stp(client)
                        write_stp(session, device_uuid, stp_result, if_index_to_db_id)
                except Exception as exc:
                    logger.warning("STP %s : %s", mgmt_ip, exc)

            session.commit()
            _finish_task(session, task, profile, "ok")
            logger.debug("✓ %s | %s | %s", scan_type, device.hostname, mgmt_ip)

    except Exception as exc:
        logger.error("ERREUR worker_monitoring %s : %s", label, exc, exc_info=True)
        try:
            with Session(engine) as session:
                task = session.get(DeviceMonitoringTask, (device_uuid, profile_id))
                if task:
                    _finish_task(session, task,
                                 session.get(MonitoringProfile, profile_id),
                                 "failed", str(exc))
        except Exception:
            pass


def _finish_task(
    session: Session,
    task: "DeviceMonitoringTask",
    profile: "MonitoringProfile | None",
    status: str,
    error: str | None = None,
) -> None:
    """Met à jour last_run_status et next_run_at après un check."""
    now = datetime.now(tz=timezone.utc)
    task.last_run_at     = now
    task.last_run_status = status
    task.last_error      = error

    if status == "ok":
        task.consecutive_failures = 0
    else:
        task.consecutive_failures = (task.consecutive_failures or 0) + 1

    if profile and profile.interval_seconds > 0:
        task.next_run_at = now + timedelta(seconds=profile.interval_seconds)
    else:
        task.next_run_at = None   # tâche unique

    try:
        session.flush()
        session.commit()
    except Exception as exc:
        logger.error("_finish_task flush error : %s", exc)
        session.rollback()


# ---------------------------------------------------------------------------
# Orchestrateur principal
# ---------------------------------------------------------------------------

def run() -> None:
    """
    Boucle principale de l'orchestrateur.

    Tourne indéfiniment jusqu'à SIGTERM/SIGINT.
    Toutes les POLL_INTERVAL secondes, soumet les scans éligibles
    dans le ThreadPoolExecutor sans attendre leur fin.
    """
    logger.info("═" * 56)
    logger.info("  Orion Collector — orchestrateur")
    logger.info("  poll=%ds  max_scans=%d", POLL_INTERVAL, MAX_CONCURRENT_SCANS)
    logger.info("═" * 56)

    # Attente DB
    logger.info("Vérification de la connexion à la base de données…")
    wait_count = 0
    while _running:
        if check_connection():
            logger.info("Base de données accessible.")
            break
        wait_count += 1
        logger.warning("Base inaccessible (tentative %d), retry dans 5s…", wait_count)
        time.sleep(5)

    if not _running:
        return

    try:
        engine = get_engine()
    except Exception as exc:
        logger.critical("Impossible de créer le moteur DB : %s", exc)
        sys.exit(1)

    executor = ThreadPoolExecutor(
        max_workers=MAX_CONCURRENT_SCANS,
        thread_name_prefix="orion-scan",
    )

    # Callback appelé quand un Future se termine — log les exceptions non catchées
    def _on_future_done(future: Future) -> None:
        exc = future.exception()
        if exc:
            logger.error("Thread terminé avec exception non catchée : %s", exc, exc_info=exc)

    pass_count = 0
    logger.info("Orchestrateur démarré — en attente de scans.")

    try:
        while _running:
            pass_count += 1

            # ── Bloc 1 : scan_networks (découverte / LLDP) ──────────────────
            try:
                with Session(engine) as session:
                    networks: list[ScanNetwork] = session.query(ScanNetwork).all()

                eligible = [n for n in networks if _is_eligible(n)]

                with _active_lock:
                    active_count = len(_active_scans)

                if eligible:
                    logger.info(
                        "Passe #%d — %d réseau(x) éligible(s) | %d scan(s) actif(s)",
                        pass_count, len(eligible), active_count,
                    )
                    for network in eligible:
                        if not _running:
                            break

                        scan_type = (
                            network.scan_profile.type
                            if network.scan_profile else "SNMP_Discovery"
                        )

                        # Seul SNMP_Discovery lance un worker subnet
                        # Les autres types (ICMP, SNMP_Metrics, LLDP, SNMP_Full)
                        # sont gérés via device_monitoring_tasks
                        if scan_type == "SNMP_Discovery":
                            future = executor.submit(_worker, network.id, engine)
                            logger.debug("Soumis scan   : %s (%s)", scan_type, network.subnet)
                        else:
                            logger.debug(
                                "Type %s ignoré pour scan_networks (géré par monitoring_tasks).",
                                scan_type,
                            )
                            continue

                        future.add_done_callback(_on_future_done)
                else:
                    if networks:
                        logger.debug(
                            "Passe #%d — %d réseau(x) configuré(s), aucun éligible.",
                            pass_count, len(networks),
                        )
                    else:
                        logger.debug(
                            "Passe #%d — scan_networks vide, en attente de configuration.",
                            pass_count,
                        )

            except Exception as exc:
                logger.error("Erreur scan_networks passe #%d : %s",
                             pass_count, exc, exc_info=True)

            # ── Bloc 2 : device_monitoring_tasks ────────────────────────────
            try:
                from sqlalchemy import select as _sa_select
                from orion_scanner.db.schema import DeviceMonitoringTask

                with Session(engine) as session:
                    now = datetime.now(tz=timezone.utc)
                    due_tasks = session.scalars(
                        _sa_select(DeviceMonitoringTask)
                        .where(DeviceMonitoringTask.is_enabled == True)       # noqa: E712
                        .where(DeviceMonitoringTask.last_run_status != "running")
                        .where(
                            (DeviceMonitoringTask.next_run_at == None) |      # noqa: E711
                            (DeviceMonitoringTask.next_run_at <= now)
                        )
                        .limit(MAX_CONCURRENT_SCANS * 4)
                    ).all()

                if due_tasks:
                    logger.debug(
                        "Passe #%d — %d monitoring task(s) à exécuter.",
                        pass_count, len(due_tasks),
                    )
                    for task in due_tasks:
                        if not _running:
                            break
                        task_key = (str(task.device_id), task.profile_id)
                        with _active_lock:
                            already = task_key in _active_monitoring
                        if already:
                            continue
                        with _active_lock:
                            _active_monitoring.add(task_key)

                        def _submit_monitoring(tk=task_key):
                            try:
                                _worker_monitoring(tk, engine)
                            finally:
                                with _active_lock:
                                    _active_monitoring.discard(tk)

                        f = executor.submit(_submit_monitoring)
                        f.add_done_callback(_on_future_done)
                # Si due_tasks est vide, on ne logue rien — comportement normal

            except Exception as exc:
                # Erreurs attendues : table vide, base pas encore peuplée → DEBUG
                # Erreurs inattendues (connexion, SQL) → WARNING
                err_str = str(exc).lower()
                if any(k in err_str for k in ("no such table", "does not exist",
                                               "relation", "undefined")):
                    logger.debug(
                        "Passe #%d — monitoring_tasks non disponibles "
                        "(tables probablement vides) : %s", pass_count, exc,
                    )
                else:
                    logger.warning(
                        "Erreur monitoring_tasks passe #%d : %s", pass_count, exc,
                    )

            # Attendre POLL_INTERVAL en restant réactif au shutdown
            for _ in range(POLL_INTERVAL):
                if not _running:
                    break
                time.sleep(1)

    finally:
        logger.info("Arrêt demandé — attente de la fin des scans en cours…")
        executor.shutdown(wait=True, cancel_futures=False)
        logger.info("Orion Collector arrêté proprement (scans effectués: %d passes).", pass_count)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
else:
    # python -m orion_scanner.collector_daemon
    try:
        run()
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)