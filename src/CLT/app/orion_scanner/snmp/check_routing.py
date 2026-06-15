"""
Check table de routage — IP-FORWARD-MIB + ipCidrRouteTable.

OIDs IP-FORWARD-MIB (RFC 2096)
--------------------------------
ipCidrRouteTable = 1.3.6.1.2.1.4.24.4.1
  Index : dest.mask.tos.nexthop
  Col 1  ipCidrRouteDest      — réseau destination
  Col 2  ipCidrRouteMask      — masque
  Col 5  ipCidrRouteNextHop   — next-hop
  Col 7  ipCidrRouteIfIndex   — ifIndex interface de sortie
  Col 9  ipCidrRouteType      — 1=other 2=reject 3=local 4=remote
  Col 10 ipCidrRouteProto     — 1=other 2=local 3=netmgmt 9=ospf 13=bgp

Fallback : ipRouteTable (RFC 1213, obsolète mais très supporté)
  1.3.6.1.2.1.4.21.1
  Col 1  ipRouteDest
  Col 2  ipRouteIfIndex
  Col 7  ipRouteNextHop
  Col 8  ipRouteType (1=other 2=invalid 3=direct 4=indirect)
  Col 11 ipRouteProto

Note : on ne remonte que les routes des protocoles utiles
(static, connected, OSPF, BGP, EIGRP).
"""

from __future__ import annotations

from dataclasses import dataclass

from orion_scanner.snmp.client import SnmpClient, SnmpError
from orion_scanner.utils.logger import get_logger

logger = get_logger(__name__)

# IP-FORWARD-MIB
_IP_CIDR_ROUTE    = "1.3.6.1.2.1.4.24.4.1"
_CIDR_COL_DEST    = 1
_CIDR_COL_MASK    = 2
_CIDR_COL_NEXTHOP = 5
_CIDR_COL_IFINDEX = 7
_CIDR_COL_PROTO   = 10

# ipRouteTable (fallback RFC 1213)
_IP_ROUTE_TABLE   = "1.3.6.1.2.1.4.21.1"
_RT_COL_DEST      = 1
_RT_COL_IFINDEX   = 2
_RT_COL_NEXTHOP   = 7
_RT_COL_PROTO     = 11

# Mapping protocole SNMP → slug DB
_PROTO_MAP = {
    "1": "other",
    "2": "local",     # connected
    "3": "static",    # netmgmt
    "9": "ospf",
    "13": "bgp",
    "16": "eigrp",    # Cisco
}

# Protocoles à conserver (exclut "other" qui génère du bruit)
_KEEP_PROTOCOLS = {"local", "static", "ospf", "bgp", "eigrp"}


@dataclass
class RouteEntry:
    """Une entrée de table de routage."""
    dest_net:    str            # ex: "10.0.0.0/24"
    next_hop:    str | None     # ex: "192.168.1.1"
    if_index:    int | None
    protocol:    str = "static"


def _walk(client: SnmpClient, oid: str) -> dict[str, str]:
    """Walk une colonne, retourne {suffix: value}."""
    full_prefix = oid + "."
    try:
        rows = client.walk(oid)
    except SnmpError as exc:
        logger.debug("Walk %s : %s", oid, exc)
        return {}
    result: dict[str, str] = {}
    for full_oid, value in rows:
        if not value or value.lower().startswith("no such"):
            continue
        if full_oid.startswith(full_prefix):
            suffix = full_oid[len(full_prefix):]
            result[suffix] = value.strip()
    return result


def _mask_to_prefix(mask: str) -> int:
    """Convertit un masque dotted-decimal en longueur de préfixe."""
    try:
        parts = [int(p) for p in mask.split(".")]
        bits = sum(bin(p).count("1") for p in parts)
        return bits
    except Exception:
        return 32


def _is_valid_ip(raw: str | None) -> str | None:
    """
    Valide qu'une valeur SNMP est bien une adresse IP dotted-decimal.

    Les colonnes IpAddress SNMP (ipCidrRouteDest, ipCidrRouteNextHop…)
    peuvent parfois retourner l'OID-suffix (un entier ou une séquence
    d'octets) plutôt qu'une IP formatée, selon l'implémentation pysnmp.
    On rejette tout ce qui n'est pas "x.x.x.x" avec 4 octets valides.
    """
    if not raw or raw in ("0.0.0.0", ""):
        return None
    parts = raw.split(".")
    if len(parts) != 4:
        return None
    try:
        octets = [int(p) for p in parts]
        if all(0 <= o <= 255 for o in octets):
            return raw
    except ValueError:
        pass
    return None


def _collect_cidr(client: SnmpClient) -> list[RouteEntry]:
    """IP-FORWARD-MIB ipCidrRouteTable."""
    base = _IP_CIDR_ROUTE

    dests    = _walk(client, f"{base}.{_CIDR_COL_DEST}")
    if not dests:
        return []

    masks    = _walk(client, f"{base}.{_CIDR_COL_MASK}")
    nexthops = _walk(client, f"{base}.{_CIDR_COL_NEXTHOP}")
    ifidxs   = _walk(client, f"{base}.{_CIDR_COL_IFINDEX}")
    protos   = _walk(client, f"{base}.{_CIDR_COL_PROTO}")

    results: list[RouteEntry] = []
    for suffix, dest_val in dests.items():
        proto_raw = protos.get(suffix, "3")
        proto     = _PROTO_MAP.get(proto_raw, "static")
        if proto not in _KEEP_PROTOCOLS:
            continue

        mask    = masks.get(suffix, "255.255.255.255")
        prefix  = _mask_to_prefix(mask)
        dest_net = f"{dest_val}/{prefix}"

        next_hop = _is_valid_ip(nexthops.get(suffix))

        if_idx_raw = ifidxs.get(suffix)
        if_index   = int(if_idx_raw) if if_idx_raw and if_idx_raw.isdigit() else None
        if if_index == 0:
            if_index = None

        results.append(RouteEntry(
            dest_net = dest_net,
            next_hop = next_hop,
            if_index = if_index,
            protocol = proto,
        ))

    logger.debug("Routing (CIDR) : %d routes sur %s.", len(results), client.ip)
    return results


def _collect_rfc1213(client: SnmpClient) -> list[RouteEntry]:
    """ipRouteTable fallback (RFC 1213)."""
    base = _IP_ROUTE_TABLE

    dests = _walk(client, f"{base}.{_RT_COL_DEST}")
    if not dests:
        return []

    ifidxs   = _walk(client, f"{base}.{_RT_COL_IFINDEX}")
    nexthops = _walk(client, f"{base}.{_RT_COL_NEXTHOP}")
    protos   = _walk(client, f"{base}.{_RT_COL_PROTO}")

    # RFC 1213 n'a pas le masque dans la table — on infère /32 sauf si
    # la dest termine par .0 (heuristique basique)
    results: list[RouteEntry] = []
    for suffix, dest_val in dests.items():
        if dest_val in ("0.0.0.0",) and suffix == "0.0.0.0":
            dest_net = "0.0.0.0/0"   # default route
        elif dest_val.endswith(".0"):
            dest_net = f"{dest_val}/24"  # heuristique
        else:
            dest_net = f"{dest_val}/32"

        proto_raw = protos.get(suffix, "3")
        proto     = _PROTO_MAP.get(proto_raw, "static")

        next_hop = _is_valid_ip(nexthops.get(suffix))

        if_idx_raw = ifidxs.get(suffix)
        if_index   = int(if_idx_raw) if if_idx_raw and if_idx_raw.isdigit() else None

        results.append(RouteEntry(
            dest_net = dest_net,
            next_hop = next_hop,
            if_index = if_index,
            protocol = proto,
        ))

    logger.debug("Routing (RFC1213) : %d routes sur %s.", len(results), client.ip)
    return results


def check_routing(client: SnmpClient) -> list[RouteEntry]:
    """
    Collecte la table de routage IP.

    Tente IP-FORWARD-MIB (CIDR) en premier, fallback RFC 1213.

    Args:
        client: Client SNMP configuré.

    Returns:
        Liste de :class:`RouteEntry`, protocoles utiles uniquement.
    """
    routes = _collect_cidr(client)
    if not routes:
        routes = _collect_rfc1213(client)

    # Dédoublonner sur dest_net + next_hop
    seen: set[tuple] = set()
    unique: list[RouteEntry] = []
    for r in routes:
        key = (r.dest_net, r.next_hop or "")
        if key not in seen:
            seen.add(key)
            unique.append(r)

    logger.debug("Routing total : %d routes uniques sur %s.", len(unique), client.ip)
    return unique