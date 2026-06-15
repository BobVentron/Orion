"""
IF-MIB interfaces collector (RFC 2863 + RFC 2233).

Tables walked
-------------
- ifTable      1.3.6.1.2.1.2.2       (index, descr, type, mtu, physAddress,
                                       adminStatus, operStatus)
- ifXTable     1.3.6.1.2.1.31.1.1    (ifName, ifAlias, ifHighSpeed)
- ipAddrTable  1.3.6.1.2.1.4.20      (IP address per interface)

ifType integer -> string mapping is intentionally minimal; only the values
commonly encountered on switches/routers are translated.
"""

import re

from orion_scanner.models import IfAdminStatus, IfOperStatus, InterfaceInfo, IpAddressInfo
from orion_scanner.snmp.client import SnmpClient, SnmpError
from orion_scanner.utils.logger import get_logger

logger = get_logger(__name__)

# --- OID prefixes (no trailing dot) ----------------------------------------

_OID_IF_TABLE = "1.3.6.1.2.1.2.2.1"
_OID_IF_INDEX = "1.3.6.1.2.1.2.2.1.1"
_OID_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
_OID_IF_TYPE = "1.3.6.1.2.1.2.2.1.3"
_OID_IF_MTU = "1.3.6.1.2.1.2.2.1.4"
_OID_IF_PHYS_ADDRESS = "1.3.6.1.2.1.2.2.1.6"
_OID_IF_ADMIN_STATUS = "1.3.6.1.2.1.2.2.1.7"
_OID_IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"

# ifXTable
_OID_IF_NAME = "1.3.6.1.2.1.31.1.1.1.1"
_OID_IF_ALIAS = "1.3.6.1.2.1.31.1.1.1.18"
_OID_IF_HIGH_SPEED = "1.3.6.1.2.1.31.1.1.1.15"  # Mbps

# ipAddrTable
_OID_IP_AD_ENT_ADDR = "1.3.6.1.2.1.4.20.1.1"
_OID_IP_AD_ENT_IF_INDEX = "1.3.6.1.2.1.4.20.1.2"
_OID_IP_AD_ENT_NET_MASK = "1.3.6.1.2.1.4.20.1.3"

# Relevant ifType values (IANAifType)
_IF_TYPE_MAP: dict[str, str] = {
    "6": "ethernet",
    "24": "softwareLoopback",
    "53": "propVirtual",
    "131": "ieee8023adLag",
    "161": "ieee8023adLag",
}

# adminStatus / operStatus: 1=up, 2=down
_STATUS_MAP = {"1": IfAdminStatus.UP, "2": IfAdminStatus.DOWN}
_OPER_MAP = {"1": IfOperStatus.UP, "2": IfOperStatus.DOWN}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _last_index(oid: str) -> str:
    """Return the last dotted component of an OID (i.e. the ifIndex)."""
    return oid.rsplit(".", 1)[-1]


def _normalize_mac(raw: str | None) -> str | None:
    """
    Normalise une adresse MAC au format PostgreSQL ``macaddr`` : ``xx:xx:xx:xx:xx:xx``.

    pysnmp peut retourner plusieurs formats selon la version et l'équipement :
      - ``0x081735e172c0``          (hex préfixé, 12 chiffres)
      - ``8:17:35:e1:72:c0``        (octets séparés par ':', sans zéro de tête)
      - ``08-17-35-E1-72-C0``       (séparés par tirets)
      - ``0817.35e1.72c0``          (notation Cisco en groupes de 4)
      - ``08 17 35 e1 72 c0``       (espaces)
      - chaîne vide ou uniquement des zéros → retourne None

    Retourne None si la chaîne n'est pas une MAC valide ou est nulle/vide.
    """
    if not raw:
        return None

    raw = raw.strip()

    # Cas : "0x" suivi de 12 chiffres hex (format pysnmp le plus courant en v6)
    if raw.lower().startswith("0x"):
        hex_str = raw[2:]
        if len(hex_str) == 12 and all(c in "0123456789abcdefABCDEF" for c in hex_str):
            return ":".join(hex_str[i:i+2].lower() for i in range(0, 12, 2))
        return None

    # Supprime les séparateurs connus pour obtenir 12 chiffres hex bruts
    cleaned = re.sub(r"[:\-\. ]", "", raw).lower()

    if len(cleaned) != 12 or not all(c in "0123456789abcdef" for c in cleaned):
        return None

    # MAC tout-zéro = pas d'adresse physique (loopback, tunnel, etc.)
    if cleaned == "000000000000":
        return None

    return ":".join(cleaned[i:i+2] for i in range(0, 12, 2))


def _normalize_iftype(raw_type: str | None) -> str | None:
    """
    Retourne le libellé du type d'interface, tronqué à 50 chars max.
    Retourne None si vide.
    """
    if not raw_type:
        return None
    return raw_type[:50]


def _walk_column(client: SnmpClient, oid_prefix: str) -> dict[str, str]:
    """
    Walk a single MIB column and return a ``{index: value}`` dict.

    A 'No Such Object' sentinel from pysnmp is treated as an empty result.
    """
    try:
        rows = client.walk(oid_prefix)
    except SnmpError as exc:
        logger.debug("Walk failed for %s on %s: %s", oid_prefix, client.ip, exc)
        return {}

    result: dict[str, str] = {}
    for oid, value in rows:
        if value.lower().startswith("no such"):
            continue
        idx = _last_index(oid)
        result[idx] = value.strip()
    return result


# ---------------------------------------------------------------------------
# Public collectors
# ---------------------------------------------------------------------------


def collect_interfaces(client: SnmpClient) -> list[InterfaceInfo]:
    """
    Collect the interface inventory from IF-MIB (ifTable + ifXTable).

    Args:
        client: A configured :class:`~orion_scanner.snmp.client.SnmpClient`.

    Returns:
        List of :class:`~orion_scanner.models.InterfaceInfo`, one per interface.
        Returns an empty list if the walk fails entirely.
    """
    # Walk core ifTable columns
    descrs = _walk_column(client, _OID_IF_DESCR)
    types = _walk_column(client, _OID_IF_TYPE)
    mtus = _walk_column(client, _OID_IF_MTU)
    macs = _walk_column(client, _OID_IF_PHYS_ADDRESS)
    admin_statuses = _walk_column(client, _OID_IF_ADMIN_STATUS)
    oper_statuses = _walk_column(client, _OID_IF_OPER_STATUS)

    # Walk ifXTable columns (may be absent on old devices)
    names = _walk_column(client, _OID_IF_NAME)
    aliases = _walk_column(client, _OID_IF_ALIAS)
    high_speeds = _walk_column(client, _OID_IF_HIGH_SPEED)

    # Build interface objects keyed by ifIndex
    all_indexes = set(descrs) | set(names)
    interfaces: list[InterfaceInfo] = []

    for idx in sorted(all_indexes, key=lambda x: int(x) if x.isdigit() else 0):
        raw_speed = high_speeds.get(idx)
        speed_bps: int | None = None
        if raw_speed and raw_speed.isdigit():
            speed_bps = int(raw_speed) * 1_000_000  # Mbps -> bps

        raw_type = types.get(idx, "")
        if_type = _IF_TYPE_MAP.get(raw_type, raw_type or None)

        raw_mtu = mtus.get(idx)
        mtu = int(raw_mtu) if raw_mtu and raw_mtu.isdigit() else None

        interface = InterfaceInfo(
            if_index=int(idx) if idx.isdigit() else 0,
            name=names.get(idx) or descrs.get(idx),
            description=descrs.get(idx),
            alias=aliases.get(idx) or None,
            mac_address=_normalize_mac(macs.get(idx)),
            if_type=_normalize_iftype(_IF_TYPE_MAP.get(raw_type, raw_type or None)),
            mtu=mtu,
            speed_bps=speed_bps,
            admin_status=_STATUS_MAP.get(admin_statuses.get(idx, ""), None),
            oper_status=_OPER_MAP.get(oper_statuses.get(idx, ""), None),
        )
        interfaces.append(interface)

    logger.debug("Collected %d interfaces from %s", len(interfaces), client.ip)
    return interfaces


def collect_ip_addresses(client: SnmpClient) -> list[IpAddressInfo]:
    """
    Collect IPv4 addresses from IP-MIB ipAddrTable.

    Args:
        client: A configured :class:`~orion_scanner.snmp.client.SnmpClient`.

    Returns:
        List of :class:`~orion_scanner.models.IpAddressInfo`.
    """
    addresses = _walk_column(client, _OID_IP_AD_ENT_ADDR)
    if_indexes = _walk_column(client, _OID_IP_AD_ENT_IF_INDEX)
    netmasks = _walk_column(client, _OID_IP_AD_ENT_NET_MASK)

    # ipAddrTable is indexed by IP address (last 4 components of OID)
    # After walking _OID_IP_AD_ENT_ADDR, the "index" is already the IP itself
    results: list[IpAddressInfo] = []

    for ip_idx, ip_val in addresses.items():
        # ip_idx looks like "192.168.1.1" (the trailing OID components)
        if_index_str = if_indexes.get(ip_idx, "0")
        netmask = netmasks.get(ip_idx, "")

        try:
            if_index = int(if_index_str)
        except ValueError:
            if_index = 0

        results.append(IpAddressInfo(
            address=ip_val,
            netmask=netmask,
            if_index=if_index,
        ))

    logger.debug("Collected %d IP addresses from %s", len(results), client.ip)
    return results
