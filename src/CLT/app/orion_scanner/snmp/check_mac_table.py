"""
Check MAC table — collecteur FDB (Forwarding Database).

Collecte la table d'adresses MAC apprise sur chaque interface via
Q-BRIDGE-MIB dot1qTpFdbTable (standard IEEE) avec fallback sur
BRIDGE-MIB dot1dTpFdbTable (plus ancien).

OIDs Q-BRIDGE-MIB (1.3.6.1.2.1.17.7.1.2.2)
--------------------------------------------
  Col 2  dot1qTpFdbPort    — ifIndex de l'interface qui a appris la MAC
  Col 3  dot1qTpFdbStatus  — 3=learned, 5=self (MAC propre du switch)
  Index  = vlan_id.mac_octet1.mac_octet2...mac_octet6

OIDs BRIDGE-MIB (1.3.6.1.2.1.17.4.3)
--------------------------------------
  Col 2  dot1dTpFdbPort    — bridge port number (≠ ifIndex, nécessite mapping)
  Col 3  dot1dTpFdbStatus  — 3=learned, 5=self
  Index  = mac_octet1...mac_octet6

  Mapping bridge port → ifIndex via dot1dBasePortIfIndex (1.3.6.1.2.1.17.1.4.1.2)
"""

from __future__ import annotations

from orion_scanner.models import MacTableEntry
from orion_scanner.snmp.client import SnmpClient, SnmpError
from orion_scanner.utils.logger import get_logger

logger = get_logger(__name__)

# Q-BRIDGE-MIB
_DOT1Q_FDB_TABLE  = "1.3.6.1.2.1.17.7.1.2.2.1"
_DOT1Q_COL_PORT   = 2
_DOT1Q_COL_STATUS = 3

# BRIDGE-MIB (fallback)
_DOT1D_FDB_TABLE     = "1.3.6.1.2.1.17.4.3.1"
_DOT1D_COL_PORT      = 2
_DOT1D_COL_STATUS    = 3
_DOT1D_PORTIFINDEX   = "1.3.6.1.2.1.17.1.4.1.2"

# Status : 3=learned, 5=self — on garde les deux
_USEFUL_STATUSES = {"3", "5"}
_STATUS_MAP = {"3": "Dynamic", "5": "Self"}


def _walk(client: SnmpClient, oid: str) -> list[tuple[str, str]]:
    try:
        return client.walk(oid)
    except SnmpError as exc:
        logger.debug("Walk %s sur %s échoué: %s", oid, client.ip, exc)
        return []


def _mac_from_oid_suffix(suffix: str) -> str | None:
    """
    Convertit un suffixe OID décimal en adresse MAC xx:xx:xx:xx:xx:xx.

    Q-BRIDGE suffix : vlan.b1.b2.b3.b4.b5.b6  → prend les 6 derniers
    BRIDGE suffix   : b1.b2.b3.b4.b5.b6
    """
    parts = suffix.split(".")
    # Prendre les 6 derniers composants
    octets = parts[-6:]
    if len(octets) != 6:
        return None
    try:
        return ":".join(f"{int(o):02x}" for o in octets)
    except ValueError:
        return None


def _collect_dot1q(client: SnmpClient) -> dict[str, MacTableEntry]:
    """Collecte via Q-BRIDGE-MIB. Retourne {mac: MacTableEntry}."""
    base = _DOT1Q_FDB_TABLE

    ports_raw   = _walk(client, f"{base}.{_DOT1Q_COL_PORT}")
    statuses_raw = {
        oid.split(f"{base}.{_DOT1Q_COL_STATUS}.")[-1]: v
        for oid, v in _walk(client, f"{base}.{_DOT1Q_COL_STATUS}")
    }

    if not ports_raw:
        return {}

    result: dict[str, MacTableEntry] = {}
    port_base = f"{base}.{_DOT1Q_COL_PORT}."

    for full_oid, port_str in ports_raw:
        if not full_oid.startswith(port_base):
            continue
        suffix = full_oid[len(port_base):]
        mac = _mac_from_oid_suffix(suffix)
        if not mac:
            continue

        status_raw = statuses_raw.get(suffix, "3")
        if status_raw not in _USEFUL_STATUSES:
            continue

        try:
            bridge_port = int(port_str)
        except ValueError:
            continue

        result[mac] = MacTableEntry(
            mac_address=mac,
            bridge_port=bridge_port,
            if_index=bridge_port,   # Q-BRIDGE retourne directement l'ifIndex
            entry_type=_STATUS_MAP.get(status_raw, "Dynamic"),
        )

    logger.debug("Q-BRIDGE FDB: %d entrées sur %s.", len(result), client.ip)
    return result


def _collect_dot1d(client: SnmpClient) -> dict[str, MacTableEntry]:
    """
    Collecte via BRIDGE-MIB (fallback).

    Les bridge port numbers doivent être mappés vers les ifIndex via
    dot1dBasePortIfIndex.
    """
    base = _DOT1D_FDB_TABLE

    ports_raw    = _walk(client, f"{base}.{_DOT1D_COL_PORT}")
    statuses_raw = {
        oid.split(f"{base}.{_DOT1D_COL_STATUS}.")[-1]: v
        for oid, v in _walk(client, f"{base}.{_DOT1D_COL_STATUS}")
    }

    if not ports_raw:
        return {}

    # Construire le mapping bridge_port → ifIndex
    port_to_ifindex: dict[int, int] = {}
    for oid, val in _walk(client, _DOT1D_PORTIFINDEX):
        bridge_port_str = oid.rsplit(".", 1)[-1]
        try:
            port_to_ifindex[int(bridge_port_str)] = int(val)
        except ValueError:
            pass

    result: dict[str, MacTableEntry] = {}
    port_base = f"{base}.{_DOT1D_COL_PORT}."

    for full_oid, port_str in ports_raw:
        if not full_oid.startswith(port_base):
            continue
        suffix = full_oid[len(port_base):]
        mac = _mac_from_oid_suffix(suffix)
        if not mac:
            continue

        status_raw = statuses_raw.get(suffix, "3")
        if status_raw not in _USEFUL_STATUSES:
            continue

        try:
            bridge_port = int(port_str)
        except ValueError:
            continue

        if_index = port_to_ifindex.get(bridge_port, bridge_port)

        result[mac] = MacTableEntry(
            mac_address=mac,
            bridge_port=bridge_port,
            if_index=if_index,
            entry_type=_STATUS_MAP.get(status_raw, "Dynamic"),
        )

    logger.debug("BRIDGE-MIB FDB: %d entrées sur %s.", len(result), client.ip)
    return result


def check_mac_table(client: SnmpClient) -> list[MacTableEntry]:
    """
    Collecte la table FDB complète d'un équipement.

    Tente Q-BRIDGE-MIB en premier (plus précis, inclut le VLAN).
    Fallback sur BRIDGE-MIB si Q-BRIDGE absent ou vide.

    Args:
        client: Client SNMP configuré.

    Returns:
        Liste de :class:`~orion_scanner.models.MacTableEntry`.
        Liste vide si l'équipement ne supporte pas les MIBs BRIDGE.
    """
    entries = _collect_dot1q(client)
    if not entries:
        entries = _collect_dot1d(client)

    result = list(entries.values())
    logger.debug("FDB total: %d entrées sur %s.", len(result), client.ip)
    return result
