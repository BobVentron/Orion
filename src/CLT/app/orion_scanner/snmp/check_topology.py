"""
Check topologie — collecte LLDP/CDP et résolution des network_links.

Ce module est responsable de :
1. Collecter les voisins LLDP/CDP de tous les équipements connus en base
2. Résoudre les remote_chassis_id → devices en base
3. Résoudre les remote_port_id → interfaces en base
4. Construire/mettre à jour network_links avec normalisation src < dst

Normalisation des liens
-----------------------
Pour éviter les doublons (A→B et B→A décrivent le même câble), on impose :
    src_interface_id < dst_interface_id (comparaison d'entiers BIGINT)

Résolution du remote_chassis_id
---------------------------------
LLDP reporte le chassis ID sous différents formats :
- MAC address (type 4) : "08:17:35:e1:72:c0"
- Locally assigned (type 7) : nom ou IP

Stratégie de résolution dans l'ordre :
1. Chercher un device dont une interface a cette MAC (vendor_oui + mac_address)
2. Chercher un device dont le hostname = remote_sysname
3. Chercher un device dont une IP = remote_ip (CDP)

Résolution du remote_port_id
------------------------------
1. Chercher par nom d'interface exact (ifName = remote_port_id)
2. Chercher par description (ifDescr = remote_port_id)
3. Chercher par alias (ifAlias = remote_port_id)
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from orion_scanner.db.schema import Device, Interface, IpAddress, LldpNeighbor, NetworkLink
from orion_scanner.models import LldpNeighbor as LldpNeighborModel
from orion_scanner.utils.logger import get_logger

logger = get_logger(__name__)

# Protocole de découverte → valeur DB
_PROTO_MAP = {"LLDP": "LLDP", "CDP": "CDP"}

_MAC_PATTERN = re.compile(
    r"^([0-9a-fA-F]{2}[:\-]){5}[0-9a-fA-F]{2}$"
)


# ---------------------------------------------------------------------------
# Résolution chassis → device
# ---------------------------------------------------------------------------

def _normalize_mac(raw: str) -> str | None:
    """Normalise une MAC en xx:xx:xx:xx:xx:xx."""
    if not raw:
        return None
    cleaned = re.sub(r"[:\-\. ]", "", raw.lower())
    if len(cleaned) == 12 and all(c in "0123456789abcdef" for c in cleaned):
        return ":".join(cleaned[i:i+2] for i in range(0, 12, 2))
    return None


def _normalize_hostname(name: str) -> str:
    """Normalise un hostname pour comparaison : minuscules, sans domaine."""
    name = name.strip().lower()
    # Retirer le domaine si FQDN (garder juste le label de gauche)
    return name.split(".")[0]


def _resolve_chassis_to_device(
    session: Session,
    remote_chassis_id: str | None,
    remote_sysname: str | None,
    remote_ip: str | None,
) -> Device | None:
    """
    Résout un voisin LLDP/CDP vers un Device connu en base.

    Ordre de tentatives :
    1. MAC address dans interfaces.mac_address (chassis_id)
    2. Sysname exact (FQDN ou hostname court, insensible à la casse)
    3. Hostname court vs hostname court en base
    4. IP dans ip_addresses (toutes les IPs, pas seulement primaire)
    5. IP dans ip_interface_map sans restriction is_primary
    """
    # 1. Résolution par MAC (chassis_id de type MAC)
    if remote_chassis_id:
        mac = _normalize_mac(remote_chassis_id)
        if mac:
            iface = session.scalar(
                select(Interface).where(Interface.mac_address == mac)
            )
            if iface:
                device = session.get(Device, iface.device_id)
                if device:
                    logger.debug("Résolu via MAC %s → %s", mac, device.hostname)
                    return device

    # 2. Résolution par sysname — plusieurs stratégies
    if remote_sysname:
        remote_short = _normalize_hostname(remote_sysname)

        # a. Match exact insensible à la casse (FQDN complet)
        device = session.scalar(
            select(Device).where(Device.hostname.ilike(remote_sysname.strip()))
        )
        if device:
            logger.debug("Résolu via sysname exact '%s' → %s", remote_sysname, device.hostname)
            return device

        # b. Hostname court vs hostname court en base (ignore le domaine des deux côtés)
        # Récupère tous les devices et compare les parties courtes
        # Optimisé : filtre SQL sur le début du hostname
        device = session.scalar(
            select(Device).where(
                Device.hostname.ilike(f"{remote_short}%")
            )
        )
        if device:
            # Vérifier que le match est bien sur le hostname court (pas un préfixe trompeur)
            db_short = _normalize_hostname(device.hostname)
            if db_short == remote_short:
                logger.debug("Résolu via hostname court '%s' → %s", remote_short, device.hostname)
                return device

        # c. Recherche partielle (le hostname en base contient le sysname ou vice-versa)
        device = session.scalar(
            select(Device).where(Device.hostname.ilike(f"%{remote_short}%"))
        )
        if device:
            logger.debug("Résolu via hostname partiel '%s' → %s", remote_short, device.hostname)
            return device

    # 3. Résolution par IP — chercher dans TOUTES les IPs du device, pas seulement primaire
    if remote_ip:
        # Normaliser l'IP (enlever le masque si présent)
        ip_clean = remote_ip.split("/")[0].strip()
        from orion_scanner.db.schema import IpInterfaceMap

        # Utiliser host() PostgreSQL pour comparer l'IP sans le masque
        from sqlalchemy import text as sa_text
        row = session.execute(
            sa_text("SELECT id FROM ip_addresses WHERE host(address) = :ip LIMIT 1"),
            {"ip": ip_clean}
        ).fetchone()
        ip_row = session.get(IpAddress, row[0]) if row else None

        if ip_row:
            # Chercher l'interface liée, peu importe is_primary
            map_row = session.scalar(
                select(IpInterfaceMap)
                .where(IpInterfaceMap.ip_address_id == ip_row.id)
            )
            if map_row:
                iface = session.get(Interface, map_row.interface_id)
                if iface:
                    device = session.get(Device, iface.device_id)
                    if device:
                        logger.debug("Résolu via IP %s → %s", ip_clean, device.hostname)
                        return device

    logger.debug(
        "Voisin non résolu : sysname='%s' chassis='%s' ip='%s'",
        remote_sysname, remote_chassis_id, remote_ip,
    )
    return None


# ---------------------------------------------------------------------------
# Résolution remote_port → interface
# ---------------------------------------------------------------------------

def _resolve_remote_port(
    session: Session,
    device: Device,
    remote_port_id: str | None,
) -> Interface | None:
    """
    Résout le remote_port_id LLDP vers une Interface en base.

    Cherche dans l'ordre : name exact → description → alias → ifIndex numérique.
    """
    if not remote_port_id:
        return None

    rp = remote_port_id.strip()

    # 1. Nom exact (ifName)
    iface = session.scalar(
        select(Interface).where(
            Interface.device_id == device.id,
            Interface.name == rp,
        )
    )
    if iface:
        return iface

    # 2. Description (ifDescr)
    iface = session.scalar(
        select(Interface).where(
            Interface.device_id == device.id,
            Interface.description == rp,
        )
    )
    if iface:
        return iface

    # 3. Alias (ifAlias)
    iface = session.scalar(
        select(Interface).where(
            Interface.device_id == device.id,
            Interface.alias == rp,
        )
    )
    if iface:
        return iface

    # 4. Contient le port_id (ex: "GigabitEthernet0/0/1" → "Gi0/0/1")
    iface = session.scalar(
        select(Interface).where(
            Interface.device_id == device.id,
            Interface.name.ilike(f"%{rp}%"),
        )
    )
    if iface:
        return iface

    logger.debug(
        "Port '%s' non résolu pour device %s.", rp, device.hostname
    )
    return None


# ---------------------------------------------------------------------------
# Upsert network_links normalisé
# ---------------------------------------------------------------------------

def upsert_network_link(
    session: Session,
    if_a_id: int,
    if_b_id: int,
    proto: str,
) -> NetworkLink | None:
    """
    Crée ou met à jour un network_link avec normalisation src < dst.

    La normalisation garantit qu'un lien découvert depuis A vers B et
    depuis B vers A produisent exactement la même ligne en base.

    Args:
        session:  Session SQLAlchemy active.
        if_a_id:  ID d'une des deux interfaces.
        if_b_id:  ID de l'autre interface.
        proto:    Protocole de découverte ('LLDP' ou 'CDP').

    Returns:
        Instance :class:`~orion_scanner.db.schema.NetworkLink` ou None si
        if_a_id == if_b_id (lien vers soi-même, ignoré).
    """
    if if_a_id == if_b_id:
        return None

    # Normalisation : le plus petit ID toujours en src
    src_id = min(if_a_id, if_b_id)
    dst_id = max(if_a_id, if_b_id)

    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from datetime import datetime, timezone

    stmt = (
        pg_insert(NetworkLink)
        .values(
            src_interface_id=src_id,
            dst_interface_id=dst_id,
            discovery_proto=proto,
            last_seen=datetime.now(tz=timezone.utc),
        )
        .on_conflict_do_update(
            constraint="uq_network_link",
            set_={
                "last_seen":       datetime.now(tz=timezone.utc),
                "discovery_proto": proto,
            },
        )
        .returning(NetworkLink.id)
    )
    row = session.execute(stmt).fetchone()
    session.flush()
    return session.get(NetworkLink, row[0]) if row else None


# ---------------------------------------------------------------------------
# Traitement des voisins d'un device
# ---------------------------------------------------------------------------

def process_lldp_neighbors(
    session: Session,
    local_device: Device,
    neighbors: list[LldpNeighborModel],
    if_index_to_db_id: dict[int, int],
) -> tuple[int, int]:
    """
    Traite les voisins LLDP/CDP d'un device et crée/met à jour les network_links.

    Pour chaque voisin :
    1. Résout remote_chassis_id → Device en base
    2. Résout remote_port_id → Interface de ce device
    3. Normalise src/dst et upsert dans network_links
    4. Met à jour lldp_neighbors (last_seen)

    Args:
        session:           Session SQLAlchemy.
        local_device:      Device local scanné.
        neighbors:         Voisins collectés par check_topology.
        if_index_to_db_id: Mapping ifIndex → interfaces.id du device local.

    Returns:
        Tuple (links_created_or_updated, unresolved_count).
    """
    resolved = 0
    unresolved = 0

    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from datetime import datetime, timezone
    from orion_scanner.db.schema import LldpNeighbor as LldpNeighborDB

    for neighbor in neighbors:
        local_if_db_id = if_index_to_db_id.get(neighbor.local_if_index)
        if local_if_db_id is None:
            logger.debug(
                "Device %s — ifIndex %d non trouvé en base.",
                local_device.hostname, neighbor.local_if_index,
            )
            unresolved += 1
            continue

        # Mettre à jour lldp_neighbors (last_seen)
        proto_str = neighbor.protocol.value if hasattr(neighbor.protocol, 'value') else str(neighbor.protocol)
        try:
            stmt_lldp = (
                pg_insert(LldpNeighborDB)
                .values(
                    local_interface_id=local_if_db_id,
                    remote_chassis_id=neighbor.remote_chassis_id,
                    remote_sysname=neighbor.remote_sys_name,
                    remote_port_id=neighbor.remote_port_id,
                    remote_ip=neighbor.remote_mgmt_ip,
                    protocol=proto_str,
                    last_seen=datetime.now(tz=timezone.utc),
                )
                .on_conflict_do_update(
                    constraint="uq_lldp_neighbor",
                    set_={
                        "last_seen":      datetime.now(tz=timezone.utc),
                        "remote_chassis_id": neighbor.remote_chassis_id,
                        "remote_ip":      neighbor.remote_mgmt_ip,
                    },
                )
            )
            session.execute(stmt_lldp)
        except Exception as exc:
            logger.debug("lldp_neighbors upsert échoué pour %s : %s",
                         local_device.hostname, exc)

        # Résoudre le voisin vers un device connu
        remote_device = _resolve_chassis_to_device(
            session,
            neighbor.remote_chassis_id,
            neighbor.remote_sys_name,
            neighbor.remote_mgmt_ip,
        )

        if remote_device is None:
            logger.debug(
                "Voisin non résolu : %s (chassis=%s) depuis %s",
                neighbor.remote_sys_name, neighbor.remote_chassis_id,
                local_device.hostname,
            )
            unresolved += 1
            continue

        if remote_device.id == local_device.id:
            logger.debug("Voisin = soi-même, ignoré (%s).", local_device.hostname)
            continue

        # Résoudre le port distant
        remote_iface = _resolve_remote_port(session, remote_device, neighbor.remote_port_id)
        if remote_iface is None:
            logger.debug(
                "Port distant non résolu : device=%s port=%s",
                remote_device.hostname, neighbor.remote_port_id,
            )
            unresolved += 1
            continue

        # Créer/mettre à jour le lien normalisé
        link = upsert_network_link(
            session, local_if_db_id, remote_iface.id, proto_str
        )
        if link:
            resolved += 1
            logger.debug(
                "Lien : %s[if%d] ↔ %s[if%d] (%s)",
                local_device.hostname, neighbor.local_if_index,
                remote_device.hostname, remote_iface.if_index,
                proto_str,
            )

    session.flush()
    return resolved, unresolved