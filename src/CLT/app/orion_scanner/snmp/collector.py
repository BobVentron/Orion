"""
SNMP scan orchestrator.

Coordinates concurrent scanning of multiple IP addresses within a
:class:`~orion_scanner.models.ScanTarget`.  Each host is scanned in its own
thread via :class:`concurrent.futures.ThreadPoolExecutor` so that I/O-bound
SNMP waits don't block the main thread.
"""

from __future__ import annotations

import concurrent.futures
from collections.abc import Callable

from orion_scanner.models import DeviceScanResult, ScanTarget
from orion_scanner.snmp.client import SnmpClient, SnmpError
from orion_scanner.snmp.entity import collect_physical_entities
from orion_scanner.snmp.interfaces import collect_interfaces, collect_ip_addresses
from orion_scanner.snmp.system import collect_system
from orion_scanner.snmp.topology import collect_topology
from orion_scanner.snmp.vlans import collect_vlans
from orion_scanner.utils.logger import get_logger
from orion_scanner.utils.network import iter_hosts

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Single-host scan
# ---------------------------------------------------------------------------


def scan_host(
    ip: str,
    target: ScanTarget,
    *,
    collect_system_info: bool = True,
    collect_interfaces_info: bool = True,
    collect_topology_info: bool = True,
    collect_entity_info: bool = True,
    collect_vlan_info: bool = True,
) -> DeviceScanResult:
    """
    Scan SNMP complet d'un hôte, avec probe de connectivité en amont.

    Étape 0 — Probe SNMP
        Un GET sur sysObjectID vérifie que l'hôte répond au SNMP avec les
        credentials fournis.  Si le probe échoue (timeout, communauté incorrecte,
        hôte éteint), on retourne immédiatement un résultat vide sans lancer
        les collectors lourds (walk, entity, vlans).

    Étapes 1-5 — Collecte complète
        Seulement si le probe réussit.

    Args:
        ip: Target IP address string.
        target: :class:`~orion_scanner.models.ScanTarget` carrying credentials
                and timing parameters.
        collect_system_info: Whether to run the System MIB collector.
        collect_interfaces_info: Whether to run IF-MIB + ipAddrTable collectors.
        collect_topology_info: Whether to run LLDP/CDP collector.
        collect_entity_info: Whether to run ENTITY-MIB collector (device_modules).
        collect_vlan_info: Whether to run VLAN collector (VTP / Q-BRIDGE).

    Returns:
        A :class:`~orion_scanner.models.DeviceScanResult` (possibly empty if
        the host did not respond to the SNMP probe).
    """
    result = DeviceScanResult(ip=ip, credentials_used=target.credentials)

    client = SnmpClient(
        ip=ip,
        credentials=target.credentials,
        timeout=target.timeout,
        retries=target.retries,
    )

    # ------------------------------------------------------------------
    # Étape 0 — Probe SNMP (GET sysObjectID)
    # Filtre rapide : évite de lancer des walks sur des hôtes qui ne
    # répondent pas au SNMP.  Chaque probe timeout = timeout secondes,
    # donc sur un /24 avec 253 hôtes et timeout=2, les hôtes muets sont
    # éliminés en ~2s chacun au lieu d'accumuler des walks sans fin.
    # ------------------------------------------------------------------
    if not client.probe():
        logger.debug("Host %s — pas de réponse SNMP (probe KO), ignoré.", ip)
        result.errors.append("SNMP probe failed (timeout or wrong community)")
        return result

    logger.debug("Host %s — probe SNMP OK, collecte complète en cours.", ip)

    # ------------------------------------------------------------------
    # Étape 1 — System MIB (sysName, sysDescr, sysObjectID…)
    # ------------------------------------------------------------------
    if collect_system_info:
        system = collect_system(client)
        if system is None:
            # Cas rare : probe OK mais collect_system échoue (MIB partiellement absente)
            logger.warning("%s — probe OK mais system collect échoué.", ip)
            result.errors.append("System MIB collection failed after successful probe")
            return result
        result.system = system

    # ------------------------------------------------------------------
    # Étape 2 — Interfaces (IF-MIB + ipAddrTable)
    # ------------------------------------------------------------------
    if collect_interfaces_info:
        try:
            result.interfaces  = collect_interfaces(client)
            result.ip_addresses = collect_ip_addresses(client)
        except SnmpError as exc:
            msg = f"Interface collection error: {exc}"
            logger.warning("%s — %s", ip, msg)
            result.errors.append(msg)

    # ------------------------------------------------------------------
    # Étape 3 — Topologie (LLDP / CDP)
    # ------------------------------------------------------------------
    if collect_topology_info:
        try:
            result.lldp_neighbors = collect_topology(client)
        except SnmpError as exc:
            msg = f"Topology collection error: {exc}"
            logger.warning("%s — %s", ip, msg)
            result.errors.append(msg)

    # ------------------------------------------------------------------
    # Étape 4 — Composants physiques (ENTITY-MIB)
    # ------------------------------------------------------------------
    if collect_entity_info:
        try:
            result.physical_entities = collect_physical_entities(client)
        except SnmpError as exc:
            msg = f"ENTITY-MIB collection error: {exc}"
            logger.warning("%s — %s", ip, msg)
            result.errors.append(msg)

    # ------------------------------------------------------------------
    # Étape 5 — VLANs (VTP / Q-BRIDGE)
    # ------------------------------------------------------------------
    if collect_vlan_info:
        try:
            result.vlans = collect_vlans(client)
        except SnmpError as exc:
            msg = f"VLAN collection error: {exc}"
            logger.warning("%s — %s", ip, msg)
            result.errors.append(msg)

    return result


# ---------------------------------------------------------------------------
# Subnet scan
# ---------------------------------------------------------------------------


def scan_target(
    target: ScanTarget,
    max_workers: int = 20,
    progress_callback: Callable[[str, DeviceScanResult], None] | None = None,
) -> list[DeviceScanResult]:
    """
    Scan every host in *target.subnet* concurrently.

    Only results where at least the system info was collected (i.e. the host
    responded to SNMP) are considered successful; all results (including
    failures) are returned so the caller can report unreachable hosts.

    Args:
        target: :class:`~orion_scanner.models.ScanTarget` describing the
                subnet, credentials, and excluded IPs.
        max_workers: Maximum concurrent threads.  Keep below ~50 to avoid
                     overwhelming small network devices.
        progress_callback: Optional callable invoked after each host scan,
                           receiving ``(ip, result)``.

    Returns:
        List of :class:`~orion_scanner.models.DeviceScanResult`, one per
        reachable host (``result.is_successful == True``).
    """
    hosts = list(iter_hosts(target.subnet, exclude=target.exclude_ips))
    total = len(hosts)
    logger.info("Starting scan of %s  (%d hosts, %d threads)", target.subnet, total, max_workers)

    successful: list[DeviceScanResult] = []
    completed = 0

    def _scan(ip: str) -> DeviceScanResult:
        return scan_host(ip, target)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ip = {executor.submit(_scan, ip): ip for ip in hosts}

        for future in concurrent.futures.as_completed(future_to_ip):
            ip = future_to_ip[future]
            completed += 1

            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                logger.error("Unexpected error scanning %s: %s", ip, exc)
                result = DeviceScanResult(
                    ip=ip,
                    credentials_used=target.credentials,
                    errors=[str(exc)],
                )

            if progress_callback:
                progress_callback(ip, result)

            if result.is_successful:
                successful.append(result)
                logger.info(
                    "[%d/%d] ✓ %s  name=%s",
                    completed, total, ip,
                    result.system.sys_name if result.system else "?",
                )
            else:
                logger.debug("[%d/%d] ✗ %s (no SNMP response)", completed, total, ip)

    logger.info(
        "Scan complete: %d/%d hosts responded to SNMP.",
        len(successful), total,
    )
    return successful
