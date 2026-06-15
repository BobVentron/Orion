"""
Collecteur de VLANs — Q-BRIDGE-MIB (IEEE) et CISCO-VTP-MIB.

Stratégie de découverte
-----------------------
On tente les deux sources dans l'ordre suivant :

1. **CISCO-VTP-MIB** (``1.3.6.1.4.1.9.9.46``) — Cisco IOS / IOS-XE.
   Remonte le nom, l'état et le type de chaque VLAN du domaine VTP.
   C'est la source la plus riche sur les équipements Cisco.

2. **Q-BRIDGE-MIB / dot1qVlanStaticTable** (``1.3.6.1.2.1.17.7.1.4.3``) —
   Standard IEEE 802.1Q, supporté par la grande majorité des switches
   (HP, Dell, Juniper, Aruba, etc.).
   Remonte le nom et l'état (active / notInService) de chaque VLAN.

Les deux sources peuvent coexister sur un même équipement Cisco ;
dans ce cas les résultats sont fusionnés, VTP ayant la priorité
sur les champs qu'il fournit.

OIDs CISCO-VTP-MIB
-------------------
vtpVlanTable = 1.3.6.1.4.1.9.9.46.1.3.1.1
  Col 2  vtpVlanState      1=operational, 2=suspended, 3=mtuTooBigForDevice…
  Col 3  vtpVlanType       1=ethernet, 2=fddi, 3=tokenRing…
  Col 4  vtpVlanName       Nom du VLAN
  (index = managementDomainIndex.vlanIndex)

OIDs Q-BRIDGE-MIB
------------------
dot1qVlanStaticTable = 1.3.6.1.2.1.17.7.1.4.3.1
  Col 1  dot1qVlanStaticName    Nom du VLAN
  Col 4  dot1qVlanStaticRowStatus  1=active, 2=notInService…
  (index = vlanIndex directement)
"""

from __future__ import annotations

from orion_scanner.models import VlanInfo
from orion_scanner.snmp.client import SnmpClient, SnmpError
from orion_scanner.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# OIDs
# ---------------------------------------------------------------------------

# CISCO-VTP-MIB
_VTP_VLAN_TABLE = "1.3.6.1.4.1.9.9.46.1.3.1.1"
_VTP_COL_STATE = 2
_VTP_COL_TYPE = 3
_VTP_COL_NAME = 4

# Q-BRIDGE-MIB
_DOT1Q_STATIC_TABLE = "1.3.6.1.2.1.17.7.1.4.3.1"
_DOT1Q_COL_NAME = 1
_DOT1Q_COL_ROW_STATUS = 4

# ---------------------------------------------------------------------------
# Mappping VTP → valeurs DB
# ---------------------------------------------------------------------------

_VTP_STATE_MAP = {
    "1": "Active",
    "2": "Suspended",
    "3": "Suspended",   # mtuTooBigForDevice → traité comme Suspended
    "4": "Suspended",   # mtuTooBigForTrunk
}

_VTP_TYPE_MAP = {
    "1": "Ethernet",
    "2": "FDDI",
    "3": "TokenRing",
    "4": "FDDI-Net",
    "5": "TrBRF",
    "6": "TrCRF",
}

# VLANs internes Cisco à ne pas remonter (1002-1005 = FDDI/TokenRing legacy)
_CISCO_RESERVED_VLANS = {1002, 1003, 1004, 1005}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _walk_col(client: SnmpClient, oid: str) -> list[tuple[str, str]]:
    """Walk une colonne et retourne les (oid, value) bruts, [] si absent."""
    try:
        return client.walk(oid)
    except SnmpError as exc:
        logger.debug("Walk %s sur %s échoué: %s", oid, client.ip, exc)
        return []


def _last_index(full_oid: str, base_oid: str) -> str:
    """Extrait le suffixe d'index après base_oid."""
    prefix = base_oid.rstrip(".") + "."
    return full_oid[len(prefix):] if full_oid.startswith(prefix) else full_oid


def _vlan_index_from_vtp(oid_suffix: str) -> int | None:
    """
    Dans VTP, l'index est ``managementDomainIndex.vlanIndex``.
    On extrait le dernier composant (= vlanIndex).
    """
    parts = oid_suffix.split(".")
    try:
        return int(parts[-1])
    except (IndexError, ValueError):
        return None


def _valid_vlan_tag(tag: int) -> bool:
    """Retourne True si le tag est dans la plage 802.1Q valide."""
    return 1 <= tag <= 4094 and tag not in _CISCO_RESERVED_VLANS


# ---------------------------------------------------------------------------
# Collecteurs par source
# ---------------------------------------------------------------------------


def _collect_vtp(client: SnmpClient) -> dict[int, VlanInfo]:
    """
    Collecte les VLANs via CISCO-VTP-MIB.

    Returns:
        Dict ``{vlan_tag: VlanInfo}``.  Vide si VTP non disponible.
    """
    col_base = _VTP_VLAN_TABLE

    names_raw = _walk_col(client, f"{col_base}.{_VTP_COL_NAME}")
    if not names_raw:
        return {}

    states_raw = dict(
        (_last_index(o, f"{col_base}.{_VTP_COL_STATE}"), v)
        for o, v in _walk_col(client, f"{col_base}.{_VTP_COL_STATE}")
    )
    types_raw = dict(
        (_last_index(o, f"{col_base}.{_VTP_COL_TYPE}"), v)
        for o, v in _walk_col(client, f"{col_base}.{_VTP_COL_TYPE}")
    )

    vlans: dict[int, VlanInfo] = {}

    for full_oid, name in names_raw:
        suffix = _last_index(full_oid, f"{col_base}.{_VTP_COL_NAME}")
        tag = _vlan_index_from_vtp(suffix)
        if tag is None or not _valid_vlan_tag(tag):
            continue

        state_raw = states_raw.get(suffix, "1")
        type_raw = types_raw.get(suffix, "1")

        vlans[tag] = VlanInfo(
            vlan_tag=tag,
            name=name if name and not name.lower().startswith("no such") else None,
            status=_VTP_STATE_MAP.get(state_raw, "Active"),
            type=_VTP_TYPE_MAP.get(type_raw, "Ethernet"),
            role="Data",  # VTP ne fournit pas le rôle ; heuristiques plus bas
        )

    logger.debug("VTP: %d VLANs collectés sur %s.", len(vlans), client.ip)
    return vlans


def _collect_dot1q(client: SnmpClient) -> dict[int, VlanInfo]:
    """
    Collecte les VLANs via Q-BRIDGE-MIB dot1qVlanStaticTable.

    Returns:
        Dict ``{vlan_tag: VlanInfo}``.  Vide si Q-BRIDGE non disponible.
    """
    col_base = _DOT1Q_STATIC_TABLE

    names_raw = _walk_col(client, f"{col_base}.{_DOT1Q_COL_NAME}")
    if not names_raw:
        return {}

    statuses_raw = dict(
        (_last_index(o, f"{col_base}.{_DOT1Q_COL_ROW_STATUS}"), v)
        for o, v in _walk_col(client, f"{col_base}.{_DOT1Q_COL_ROW_STATUS}")
    )

    vlans: dict[int, VlanInfo] = {}

    for full_oid, name in names_raw:
        suffix = _last_index(full_oid, f"{col_base}.{_DOT1Q_COL_NAME}")
        try:
            tag = int(suffix)
        except ValueError:
            continue

        if not _valid_vlan_tag(tag):
            continue

        # dot1qVlanStaticRowStatus: 1=active, autres = inactif
        row_status = statuses_raw.get(suffix, "1")
        status = "Active" if row_status == "1" else "Suspended"

        vlans[tag] = VlanInfo(
            vlan_tag=tag,
            name=name if name and not name.lower().startswith("no such") else None,
            status=status,
            type="Ethernet",
            role="Data",
        )

    logger.debug("dot1Q: %d VLANs collectés sur %s.", len(vlans), client.ip)
    return vlans


def _infer_vlan_role(vlan: VlanInfo) -> str:
    """
    Heuristique sur le nom pour déduire le rôle d'un VLAN.

    Correspond aux valeurs acceptées par la contrainte DB :
    ``Data | Voice | Management | Guest | Blackhole``.
    """
    name_lower = (vlan.name or "").lower()
    tag = vlan.vlan_tag

    if any(kw in name_lower for kw in ("voice", "voip", "voix", "phone")):
        return "Voice"
    if any(kw in name_lower for kw in ("mgmt", "manage", "admin", "oob", "ilo", "idrac")):
        return "Management"
    if any(kw in name_lower for kw in ("guest", "invite", "wifi-public", "hotspot")):
        return "Guest"
    if any(kw in name_lower for kw in ("black", "null", "trash", "quarantine")):
        return "Blackhole"
    # VLAN 1 est généralement Data (natif par défaut, non touché)
    return "Data"


# ---------------------------------------------------------------------------
# Collecteur public
# ---------------------------------------------------------------------------


def collect_vlans(client: SnmpClient) -> list[VlanInfo]:
    """
    Collecte les VLANs en combinant VTP (Cisco) et Q-BRIDGE (standard).

    VTP est tenté en premier.  dot1Q est toujours tenté et sert de
    complément ou de source unique sur les équipements non-Cisco.
    Les informations VTP ont priorité sur dot1Q pour les champs partagés.

    Args:
        client: Client SNMP configuré.

    Returns:
        Liste de :class:`~orion_scanner.models.VlanInfo`, dédupliquée et
        enrichie par l'heuristique de rôle.
        Retourne une liste vide si aucune des deux sources n'est disponible.
    """
    vtp_vlans = _collect_vtp(client)
    dot1q_vlans = _collect_dot1q(client)

    # Fusion : dot1Q en base, VTP écrase si présent
    merged: dict[int, VlanInfo] = {**dot1q_vlans, **vtp_vlans}

    if not merged:
        logger.debug("Aucun VLAN trouvé sur %s (VTP ni dot1Q).", client.ip)
        return []

    # Application de l'heuristique de rôle
    result: list[VlanInfo] = []
    for vlan in sorted(merged.values(), key=lambda v: v.vlan_tag):
        vlan.role = _infer_vlan_role(vlan)
        result.append(vlan)

    logger.debug(
        "VLANs: %d entrées uniques sur %s (vtp=%d, dot1q=%d).",
        len(result), client.ip, len(vtp_vlans), len(dot1q_vlans),
    )
    return result
