"""
Topology collector — LLDP-MIB and Cisco CDP-MIB.

LLDP OIDs (RFC 2922 / IEEE 802.1AB)
-------------------------------------
- lldpRemLocalPortNum   1.3.6.1.4.1.45813.1.1.4.1.1.1  (local ifIndex)
  NB: the standard lldpRemTable is under 1.3.6.1.4.1.45813 in the LLDP-MIB.
  We use numeric OIDs that map to:
    lldpRemTable          1.3.6.1.4.1.45813.1.1.4.1
    lldpRemLocalPortNum   column 1
    lldpRemChassisId      column 5  (chassis ID)
    lldpRemSysName        column 9
    lldpRemPortId         column 7  (port ID)
    lldpRemManAddrTable   1.3.6.1.4.1.45813.1.1.4.2  -> lldpRemManAddr column 2

  Standard MIB numeric OIDs (IEEE 802.1AB):
    lldpRemTable = 1.3.6.1.4.1.45813.1.1.4.1.1
  OR via the IETF MIB:
    lldpRemTable = 1.3.6.1.2.1.138.1.3.1  (LLDP-MIB from RFC 2922 extension)

  In practice many implementations use:
    lldpRemTable base = 1.3.6.1.4.1.45813.1.1.4.1.1
  Others use:
    lldpRemTable base = 1.3.6.1.2.1.138.1.3.1.1

  We try BOTH bases.

CDP OIDs (CISCO-CDP-MIB)
-------------------------
  cdpCacheTable     1.3.6.1.4.1.9.9.23.1.2.1.1
  cdpCacheDeviceId  column 6
  cdpCacheDevicePort column 7
  cdpCachePlatform  column 8
  cdpCacheAddress   column 4 (binary IP)
"""

import socket
import struct

from orion_scanner.models import LldpNeighbor, LldpProtocol
from orion_scanner.snmp.client import SnmpClient, SnmpError
from orion_scanner.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# LLDP OID bases (we try both)
# ---------------------------------------------------------------------------

_LLDP_REM_TABLE_BASES = [
    "1.3.6.1.4.1.45813.1.1.4.1.1",  # IEEE / many vendors
    "1.3.6.1.2.1.138.1.3.1.1",       # IETF LLDP-MIB
]

# Column offsets relative to lldpRemTable base
_COL_LOCAL_PORT_NUM = 1   # lldpRemLocalPortNum (= ifIndex on most devices)
_COL_CHASSIS_ID = 5        # lldpRemChassisId
_COL_PORT_ID = 7           # lldpRemPortId
_COL_SYS_NAME = 9          # lldpRemSysName

# CDP
_CDP_CACHE_BASE = "1.3.6.1.4.1.9.9.23.1.2.1.1"
_CDP_COL_ADDRESS = 4        # cdpCacheAddress (binary)
_CDP_COL_DEVICE_ID = 6      # cdpCacheDeviceId
_CDP_COL_DEVICE_PORT = 7    # cdpCacheDevicePort


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _walk_column(client: SnmpClient, oid_prefix: str) -> list[tuple[str, str]]:
    """Walk a column; return raw (oid, value) pairs or [] on failure."""
    try:
        return client.walk(oid_prefix)
    except SnmpError as exc:
        logger.debug("Walk %s on %s failed: %s", oid_prefix, client.ip, exc)
        return []


def _parse_cdp_ip(raw: str) -> str | None:
    """
    Convert a CDP binary address string to dotted-decimal notation.

    CDP stores addresses as a hex string like '0x C0A80101' (= 192.168.1.1).
    """
    # pysnmp renders binary as hex string: '0x c0a801fe' or raw bytes repr
    cleaned = raw.replace("0x", "").replace(" ", "").strip()
    try:
        if len(cleaned) == 8:
            packed = bytes.fromhex(cleaned)
            return socket.inet_ntoa(packed)
    except (ValueError, OSError):
        pass
    return None


def _index_suffix(full_oid: str, base_oid: str) -> str:
    """Return the OID suffix after *base_oid*."""
    prefix = base_oid.rstrip(".") + "."
    if full_oid.startswith(prefix):
        return full_oid[len(prefix):]
    return full_oid


# ---------------------------------------------------------------------------
# LLDP collector
# ---------------------------------------------------------------------------


def _collect_lldp(client: SnmpClient, table_base: str) -> list[LldpNeighbor]:
    """Attempt to collect LLDP neighbors from a given table base OID."""
    local_ports: dict[str, str] = {}
    chassis_ids: dict[str, str] = {}
    port_ids: dict[str, str] = {}
    sys_names: dict[str, str] = {}

    col_base = table_base.rstrip(".")

    for oid, val in _walk_column(client, f"{col_base}.{_COL_LOCAL_PORT_NUM}"):
        idx = _index_suffix(oid, f"{col_base}.{_COL_LOCAL_PORT_NUM}")
        local_ports[idx] = val

    if not local_ports:
        return []

    for oid, val in _walk_column(client, f"{col_base}.{_COL_CHASSIS_ID}"):
        idx = _index_suffix(oid, f"{col_base}.{_COL_CHASSIS_ID}")
        chassis_ids[idx] = val

    for oid, val in _walk_column(client, f"{col_base}.{_COL_PORT_ID}"):
        idx = _index_suffix(oid, f"{col_base}.{_COL_PORT_ID}")
        port_ids[idx] = val

    for oid, val in _walk_column(client, f"{col_base}.{_COL_SYS_NAME}"):
        idx = _index_suffix(oid, f"{col_base}.{_COL_SYS_NAME}")
        sys_names[idx] = val

    neighbors: list[LldpNeighbor] = []
    for idx, local_port_raw in local_ports.items():
        try:
            local_if_index = int(local_port_raw)
        except ValueError:
            local_if_index = 0

        neighbors.append(LldpNeighbor(
            local_if_index=local_if_index,
            remote_chassis_id=chassis_ids.get(idx),
            remote_sys_name=sys_names.get(idx),
            remote_port_id=port_ids.get(idx),
            protocol=LldpProtocol.LLDP,
        ))

    return neighbors


# ---------------------------------------------------------------------------
# CDP collector
# ---------------------------------------------------------------------------


def _collect_cdp(client: SnmpClient) -> list[LldpNeighbor]:
    """Collect Cisco CDP neighbors from CISCO-CDP-MIB."""
    addresses: dict[str, str] = {}
    device_ids: dict[str, str] = {}
    device_ports: dict[str, str] = {}

    col_base = _CDP_CACHE_BASE

    for oid, val in _walk_column(client, f"{col_base}.{_CDP_COL_ADDRESS}"):
        idx = _index_suffix(oid, f"{col_base}.{_CDP_COL_ADDRESS}")
        addresses[idx] = val

    if not addresses:
        return []

    for oid, val in _walk_column(client, f"{col_base}.{_CDP_COL_DEVICE_ID}"):
        idx = _index_suffix(oid, f"{col_base}.{_CDP_COL_DEVICE_ID}")
        device_ids[idx] = val

    for oid, val in _walk_column(client, f"{col_base}.{_CDP_COL_DEVICE_PORT}"):
        idx = _index_suffix(oid, f"{col_base}.{_CDP_COL_DEVICE_PORT}")
        device_ports[idx] = val

    neighbors: list[LldpNeighbor] = []
    for idx, raw_addr in addresses.items():
        # CDP index: ifIndex.neighborIndex
        parts = idx.split(".")
        try:
            local_if_index = int(parts[0])
        except (IndexError, ValueError):
            local_if_index = 0

        mgmt_ip = _parse_cdp_ip(raw_addr)

        neighbors.append(LldpNeighbor(
            local_if_index=local_if_index,
            remote_chassis_id=None,
            remote_sys_name=device_ids.get(idx),
            remote_port_id=device_ports.get(idx),
            remote_mgmt_ip=mgmt_ip,
            protocol=LldpProtocol.CDP,
        ))

    return neighbors


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def collect_topology(client: SnmpClient) -> list[LldpNeighbor]:
    """
    Collect L2 neighbors via LLDP and/or CDP.

    Tries LLDP first (two known OID bases), then falls back to CDP.
    Results from all successful probes are combined and de-duplicated by
    ``(local_if_index, remote_sys_name)`` to avoid duplicates when both
    protocols report the same neighbor.

    Args:
        client: A configured :class:`~orion_scanner.snmp.client.SnmpClient`.

    Returns:
        List of :class:`~orion_scanner.models.LldpNeighbor`.
    """
    neighbors: list[LldpNeighbor] = []

    # Try both LLDP bases
    for base in _LLDP_REM_TABLE_BASES:
        found = _collect_lldp(client, base)
        if found:
            logger.debug(
                "LLDP: found %d neighbors from %s (base %s)",
                len(found), client.ip, base,
            )
            neighbors.extend(found)
            break  # stop at first successful base

    # Always try CDP (may yield different/additional neighbors)
    cdp_neighbors = _collect_cdp(client)
    if cdp_neighbors:
        logger.debug("CDP: found %d neighbors from %s", len(cdp_neighbors), client.ip)
        neighbors.extend(cdp_neighbors)

    # De-duplicate by (local_if_index, remote_sys_name, protocol)
    seen: set[tuple] = set()
    unique: list[LldpNeighbor] = []
    for n in neighbors:
        key = (n.local_if_index, n.remote_sys_name, n.protocol)
        if key not in seen:
            seen.add(key)
            unique.append(n)

    logger.debug("Topology: %d unique neighbors from %s", len(unique), client.ip)
    return unique
