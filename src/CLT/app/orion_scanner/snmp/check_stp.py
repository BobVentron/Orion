"""
Check STP — collecteur Spanning Tree Protocol.

BRIDGE-MIB (RFC 1493)
-----------------------
dot1dStp = 1.3.6.1.2.1.17.2
  .1  dot1dStpProtocolSpecification   1=unknown 2=decLan 3=ieee8021d
  .2  dot1dStpPriority                Priorité du bridge local
  .4  dot1dStpRootCost                Coût jusqu'à la racine
  .5  dot1dStpRootPort                Port vers la racine
  .7  dot1dStpDesignatedRoot          MAC+priorité du root bridge (8 octets)

dot1dStpPortTable = 1.3.6.1.2.1.17.2.15.1
  Index : bridge_port_number
  Col 1  dot1dStpPort               — Numéro de port bridge
  Col 3  dot1dStpPortState          — 1=disabled 2=blocking 3=listening 4=learning 5=forwarding 6=broken
  Col 4  dot1dStpPortEnable         — 1=enabled 2=disabled
  Col 7  dot1dStpPortDesignatedRoot — Root bridge vu par ce port
  Col 8  dot1dStpPortDesignatedCost
  Col 9  dot1dStpPortDesignatedBridge
  Col 10 dot1dStpPortDesignatedPort

Mapping bridge_port → ifIndex via dot1dBasePortIfIndex (1.3.6.1.2.1.17.1.4.1.2)

IEEE 802.1s MSTP / Cisco PVST
-------------------------------
Pour le PVST Cisco, chaque VLAN a sa propre instance STP.
On accède aux instances par VLAN via la communauté @vlanId (snmpwalk -v2c -c public@10 ...)
Ce mécanisme n'est pas supporté ici — on collecte uniquement l'instance par défaut.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from orion_scanner.snmp.client import SnmpClient, SnmpError
from orion_scanner.utils.logger import get_logger

logger = get_logger(__name__)

# dot1dStp scalaires
_STP_BASE          = "1.3.6.1.2.1.17.2"
_STP_PRIORITY      = "1.3.6.1.2.1.17.2.2"
_STP_ROOT_COST     = "1.3.6.1.2.1.17.2.4"
_STP_DESIG_ROOT    = "1.3.6.1.2.1.17.2.7"   # 8 octets : 2 priorité + 6 MAC

# dot1dStpPortTable
_STP_PORT_TABLE    = "1.3.6.1.2.1.17.2.15.1"
_COL_PORT_STATE    = 3
_COL_PORT_DESIG_ROOT = 7

# dot1dBasePortIfIndex — mapping bridge_port → ifIndex
_BASE_PORT_IFINDEX = "1.3.6.1.2.1.17.1.4.1.2"

_STATE_MAP = {
    "1": "Disabled",
    "2": "Blocking",
    "3": "Listening",
    "4": "Learning",
    "5": "Forwarding",
    "6": "Disabled",  # broken → Disabled
}

# États à ignorer pour alléger (disabled = pas utile en supervision courante)
_SKIP_STATES = {"1", "6"}


@dataclass
class StpInstanceInfo:
    """Instance STP du device (instance par défaut / VLAN 1)."""
    root_bridge_id:  str | None   # ex: "0010.5a3b.1234" (MAC du root)
    bridge_priority: int | None   # priorité locale
    root_cost:       int | None   # coût total jusqu'à la racine


@dataclass
class StpPortState:
    """État STP d'un port."""
    if_index:  int
    state:     str   # Blocking | Listening | Learning | Forwarding | Disabled


@dataclass
class StpCheckResult:
    instance:   StpInstanceInfo
    port_states: list[StpPortState] = field(default_factory=list)


def _get(client: SnmpClient, oid: str) -> str | None:
    """GET SNMP simple, retourne la valeur brute ou None."""
    try:
        result = client.get(oid)
        if result and not result.lower().startswith("no such"):
            return result.strip()
    except (SnmpError, Exception) as exc:
        logger.debug("GET %s : %s", oid, exc)
    return None


def _walk(client: SnmpClient, oid: str) -> dict[str, str]:
    prefix = oid + "."
    try:
        rows = client.walk(oid)
    except SnmpError as exc:
        logger.debug("Walk %s : %s", oid, exc)
        return {}
    result: dict[str, str] = {}
    for full_oid, value in rows:
        if not value or value.lower().startswith("no such"):
            continue
        if full_oid.startswith(prefix):
            result[full_oid[len(prefix):]] = value.strip()
    return result


def _parse_bridge_id(raw: str) -> str | None:
    """
    Parse un Bridge ID SNMP (8 octets : 2 octets priorité + 6 octets MAC).

    pysnmp retourne typiquement "0x804b.3a1f.2c00" ou une séquence hex.
    On retourne "priorité.MAC" ex: "32768.4b:3a:1f:2c:00:01".
    """
    if not raw:
        return None
    cleaned = raw.replace("0x", "").replace(" ", "").replace(":", "").replace(".", "")
    if len(cleaned) < 16:
        return raw   # Retourner tel quel si format inconnu
    try:
        priority = int(cleaned[:4], 16)
        mac_hex  = cleaned[4:16]
        mac      = ":".join(mac_hex[i:i+2] for i in range(0, 12, 2))
        return f"{priority}.{mac}"
    except Exception:
        return raw


def check_stp(client: SnmpClient) -> StpCheckResult | None:
    """
    Collecte l'état STP du device (instance par défaut).

    Args:
        client: Client SNMP configuré.

    Returns:
        :class:`StpCheckResult` ou None si STP absent/non supporté.
    """
    # Récupérer les scalaires de l'instance STP
    priority_raw  = _get(client, _STP_PRIORITY)
    root_cost_raw = _get(client, _STP_ROOT_COST)
    root_id_raw   = _get(client, _STP_DESIG_ROOT)

    if priority_raw is None:
        logger.debug("STP : BRIDGE-MIB absent sur %s.", client.ip)
        return None

    instance = StpInstanceInfo(
        root_bridge_id  = _parse_bridge_id(root_id_raw),
        bridge_priority = int(priority_raw) if priority_raw and priority_raw.isdigit() else None,
        root_cost       = int(root_cost_raw) if root_cost_raw and root_cost_raw.isdigit() else None,
    )

    # Mapping bridge_port → ifIndex
    bridge_to_ifindex: dict[str, str] = _walk(client, _BASE_PORT_IFINDEX)

    # États des ports
    port_states_raw = _walk(client, f"{_STP_PORT_TABLE}.{_COL_PORT_STATE}")
    port_states: list[StpPortState] = []

    for bridge_port, state_raw in port_states_raw.items():
        if state_raw in _SKIP_STATES:
            continue  # Disabled → pas utile

        state = _STATE_MAP.get(state_raw, "Disabled")
        if_idx_raw = bridge_to_ifindex.get(bridge_port)

        if not if_idx_raw or not if_idx_raw.isdigit():
            continue

        port_states.append(StpPortState(
            if_index = int(if_idx_raw),
            state    = state,
        ))

    logger.debug(
        "STP : root=%s priority=%s %d ports sur %s.",
        instance.root_bridge_id, instance.bridge_priority,
        len(port_states), client.ip,
    )

    return StpCheckResult(instance=instance, port_states=port_states)