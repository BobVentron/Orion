"""
Check Trunks 802.1Q — collecteur interface_trunks + interface_vlans.

Sources
--------
CISCO-VTP-MIB vlanTrunkPortTable (1.3.6.1.4.1.9.9.46.1.6.1.1)
  Col 1   vlanTrunkPortManagementDomain
  Col 2   vlanTrunkPortEncapsulationType  1=isl, 4=dot1q, 5=negotiate
  Col 4   vlanTrunkPortDynamicState       1=on, 2=off, 3=desirable, 4=auto, 5=onNoNegotiate
  Col 5   vlanTrunkPortDynamicStatus      1=trunking, 2=notTrunking
  Col 10  vlanTrunkPortNativeVlan
  Col 14  vlanTrunkPortVlansEnabled       OCTET STRING bitmask (VLANs 0-1023)
  Col 17  vlanTrunkPortVlansEnabled2      OCTET STRING bitmask (VLANs 1024-2047)
  Col 18  vlanTrunkPortVlansEnabled3      (VLANs 2048-3071)
  Col 19  vlanTrunkPortVlansEnabled4      (VLANs 3072-4095)

Q-BRIDGE-MIB dot1qPortVlanTable (1.3.6.1.2.1.17.7.1.4.5.1)
  Col 1  dot1qPvid               — VLAN non-taggé (natif / access vlan)
  (+ dot1qVlanCurrentEgressPorts pour les VLANs autorisés)

dot1qPortVlanStaticTable (1.3.6.1.2.1.17.7.1.4.3.1)
  Col 2  dot1qVlanStaticEgressPorts   bitmask des ports pour ce VLAN

Décodage bitmask
-----------------
Les allowed_vlans Cisco sont encodés en OCTET STRING (bitmask) :
  Bit i du byte n = VLAN (n*8 + i) est autorisé.
  Ex: byte 0 = 0xFF → VLANs 0-7 autorisés.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from orion_scanner.snmp.client import SnmpClient, SnmpError
from orion_scanner.utils.logger import get_logger

logger = get_logger(__name__)

# CISCO-VTP-MIB vlanTrunkPortTable
_VTP_TRUNK_TABLE        = "1.3.6.1.4.1.9.9.46.1.6.1.1"
_COL_ENCAPSULATION      = 2
_COL_DYNAMIC_STATE      = 4
_COL_DYNAMIC_STATUS     = 5
_COL_NATIVE_VLAN        = 10
_COL_VLANS_ENABLED_1    = 14   # VLANs 0-1023
_COL_VLANS_ENABLED_2    = 17   # VLANs 1024-2047
_COL_VLANS_ENABLED_3    = 18   # VLANs 2048-3071
_COL_VLANS_ENABLED_4    = 19   # VLANs 3072-4095

# Q-BRIDGE-MIB
_DOT1Q_PVID             = "1.3.6.1.2.1.17.7.1.4.5.1.1"   # Port VLAN ID (access/natif)

_VTP_ENCAP_MAP = {
    "1": "isl",
    "4": "dot1q",
    "5": "negotiate",
}

_VTP_STATUS_MAP = {
    "1": "Up",    # trunking
    "2": "Down",  # notTrunking
}


@dataclass
class TrunkEntry:
    """Données d'un port trunk."""
    if_index:       int
    encapsulation:  str = "dot1q"
    admin_status:   str = "Up"
    oper_status:    str = "Down"
    native_vlan:    int | None = None
    allowed_vlans:  str = ""        # ex: "1,10,20-30,100-200"
    is_trunk:       bool = False


@dataclass
class VlanMembership:
    """Appartenance d'une interface à un VLAN."""
    if_index:  int
    vlan_tag:  int
    mode:      str = "Untagged"   # Untagged | Tagged | Native
    is_native: bool = False


@dataclass
class TrunkCheckResult:
    trunks:   list[TrunkEntry]       = field(default_factory=list)
    vlans:    list[VlanMembership]   = field(default_factory=list)


def _walk(client: SnmpClient, oid: str) -> dict[str, str]:
    try:
        rows = client.walk(oid)
    except SnmpError as exc:
        logger.debug("Walk %s sur %s : %s", oid, client.ip, exc)
        return {}
    result: dict[str, str] = {}
    for full_oid, value in rows:
        if value.lower().startswith("no such"):
            continue
        idx = full_oid.rsplit(".", 1)[-1]
        result[idx] = value.strip()
    return result


def _decode_vlan_bitmask(hex_str: str, base_vlan: int = 0) -> list[int]:
    """
    Décode un bitmask OCTET STRING Cisco en liste de VLAN IDs.

    Le bitmask est retourné par pysnmp sous forme hexadécimale : "0x..."
    Bit 7 du premier octet = VLAN base_vlan (MSB first).
    """
    if not hex_str:
        return []

    # Nettoyer le préfixe hex
    cleaned = hex_str.replace("0x", "").replace(" ", "").strip()
    if not cleaned:
        return []

    try:
        raw_bytes = bytes.fromhex(cleaned)
    except ValueError:
        return []

    vlans: list[int] = []
    for byte_idx, byte_val in enumerate(raw_bytes):
        for bit_idx in range(8):
            if byte_val & (0x80 >> bit_idx):
                vlan_id = base_vlan + byte_idx * 8 + bit_idx
                if 1 <= vlan_id <= 4094:
                    vlans.append(vlan_id)
    return vlans


def _vlans_to_range_str(vlan_list: list[int]) -> str:
    """
    Convertit une liste de VLANs en notation condensée.
    Ex: [1, 2, 3, 10, 11, 20] → "1-3,10-11,20"
    """
    if not vlan_list:
        return ""
    sorted_vlans = sorted(set(vlan_list))
    ranges: list[str] = []
    start = prev = sorted_vlans[0]

    for v in sorted_vlans[1:]:
        if v == prev + 1:
            prev = v
        else:
            ranges.append(f"{start}-{prev}" if start != prev else str(start))
            start = prev = v
    ranges.append(f"{start}-{prev}" if start != prev else str(start))
    return ",".join(ranges)


def _collect_cisco_trunks(client: SnmpClient) -> list[TrunkEntry]:
    """Collecte les trunks via CISCO-VTP-MIB."""
    base = _VTP_TRUNK_TABLE

    status_data = _walk(client, f"{base}.{_COL_DYNAMIC_STATUS}")
    if not status_data:
        return []

    encap_data   = _walk(client, f"{base}.{_COL_ENCAPSULATION}")
    state_data   = _walk(client, f"{base}.{_COL_DYNAMIC_STATE}")
    native_data  = _walk(client, f"{base}.{_COL_NATIVE_VLAN}")
    vlans1_data  = _walk(client, f"{base}.{_COL_VLANS_ENABLED_1}")
    vlans2_data  = _walk(client, f"{base}.{_COL_VLANS_ENABLED_2}")
    vlans3_data  = _walk(client, f"{base}.{_COL_VLANS_ENABLED_3}")
    vlans4_data  = _walk(client, f"{base}.{_COL_VLANS_ENABLED_4}")

    results: list[TrunkEntry] = []

    for idx, status_raw in status_data.items():
        if not idx.isdigit():
            continue

        is_trunk   = (status_raw == "1")
        encap_raw  = encap_data.get(idx, "4")
        native_raw = native_data.get(idx)

        # Décoder les VLANs autorisés depuis les 4 bitmasks
        all_vlans: list[int] = []
        if vlans1_data.get(idx):
            all_vlans.extend(_decode_vlan_bitmask(vlans1_data[idx], 0))
        if vlans2_data.get(idx):
            all_vlans.extend(_decode_vlan_bitmask(vlans2_data[idx], 1024))
        if vlans3_data.get(idx):
            all_vlans.extend(_decode_vlan_bitmask(vlans3_data[idx], 2048))
        if vlans4_data.get(idx):
            all_vlans.extend(_decode_vlan_bitmask(vlans4_data[idx], 3072))

        native_vlan = int(native_raw) if native_raw and native_raw.isdigit() else None

        results.append(TrunkEntry(
            if_index      = int(idx),
            encapsulation = _VTP_ENCAP_MAP.get(encap_raw, "dot1q"),
            admin_status  = "Up",
            oper_status   = _VTP_STATUS_MAP.get(status_raw, "Down"),
            native_vlan   = native_vlan,
            allowed_vlans = _vlans_to_range_str(all_vlans),
            is_trunk      = is_trunk,
        ))

    logger.debug(
        "Trunks (Cisco VTP) : %d interfaces, %d trunking sur %s.",
        len(results), sum(1 for t in results if t.is_trunk), client.ip,
    )
    return results


# OID pour récupérer les VLANs actifs sur chaque port trunk (plus précis que bitmask allowed)
# dot1qVlanCurrentEgressPorts = 1.3.6.1.2.1.17.7.1.4.2.1.4 (index = fdb_id.vlan_id)
# Trop complexe — on utilise dot1qTpFdbTable pour les VLANs actifs sur chaque port.
# Approche retenue : on intersecte allowed_vlans avec les VLANs déclarés sur le device.
# Cela évite l'explosion "1-4094 × N ports" quand le trunk autorise tous les VLANs.
_DOT1Q_VLAN_CURRENT_UNTAGGED = "1.3.6.1.2.1.17.7.1.4.2.1.5"  # bitmask ports untagged par VLAN


def _parse_allowed_vlans(allowed_str: str) -> set[int]:
    """Parse la chaîne allowed_vlans en ensemble d'entiers."""
    result: set[int] = set()
    for part in allowed_str.split(","):
        part = part.strip()
        if "-" in part:
            try:
                start, end = part.split("-", 1)
                result.update(range(int(start), min(int(end), 4094) + 1))
            except ValueError:
                pass
        elif part.isdigit():
            v = int(part)
            if 1 <= v <= 4094:
                result.add(v)
    return result


def _collect_vlan_memberships(
    client: SnmpClient,
    trunks: list[TrunkEntry],
) -> list[VlanMembership]:
    """
    Construit les appartenances VLAN par interface.

    Stratégie anti-explosion :
    - Ports trunk : on récupère les VLANs via dot1qVlanCurrentEgressPorts
      (bitmask des ports par VLAN — sens inverse) pour n'avoir que les VLANs
      vraiment actifs sur chaque port, pas tous les VLANs "autorisés".
    - Ports access : PVID via dot1qPortVlanTable.

    Sans cela, un trunk "allow all" (1-4094) × 10 ports = 40k lignes par device.
    """
    memberships: list[VlanMembership] = []

    trunk_if_indexes = {t.if_index for t in trunks if t.is_trunk}
    native_vlan_by_ifindex = {t.if_index: t.native_vlan for t in trunks if t.is_trunk}

    # ── Approche sens inverse : pour chaque VLAN, quels ports le portent ──
    # dot1qVlanCurrentEgressPorts (1.3.6.1.2.1.17.7.1.4.2.1.4)
    # Index = fdb_id.vlan_tag, valeur = bitmask des ports (bridge port numbers)
    # On utilise dot1qVlanCurrentUntaggedPorts pour distinguer tagged/untagged
    egress_base   = "1.3.6.1.2.1.17.7.1.4.2.1.4"
    untagged_base = "1.3.6.1.2.1.17.7.1.4.2.1.5"

    # Mapping bridge_port → ifIndex
    bridge_to_if: dict[int, int] = {}
    for oid, val in _walk(client, "1.3.6.1.2.1.17.1.4.1.2").items():
        if val.isdigit():
            bridge_port = int(oid.rsplit(".", 1)[-1])
            bridge_to_if[bridge_port] = int(val)

    egress_rows   = _walk(client, egress_base)
    untagged_rows = _walk(client, untagged_base)

    if egress_rows and bridge_to_if:
        for suffix, egress_hex in egress_rows.items():
            # suffix = "fdb_id.vlan_tag" ou juste "vlan_tag" selon l'implémentation
            parts = suffix.split(".")
            try:
                vlan_tag = int(parts[-1])
            except ValueError:
                continue
            if not (1 <= vlan_tag <= 4094):
                continue

            untagged_hex = untagged_rows.get(suffix, "")
            egress_bits   = _decode_vlan_bitmask(egress_hex,   0)
            untagged_bits = set(_decode_vlan_bitmask(untagged_hex, 0)) if untagged_hex else set()

            for bit_port in egress_bits:
                if_index = bridge_to_if.get(bit_port)
                if if_index is None:
                    continue
                is_untagged = (bit_port in untagged_bits)
                native_vlan  = native_vlan_by_ifindex.get(if_index)
                is_native    = (vlan_tag == native_vlan)
                mode = "Native" if is_native else ("Untagged" if is_untagged else "Tagged")

                memberships.append(VlanMembership(
                    if_index  = if_index,
                    vlan_tag  = vlan_tag,
                    mode      = mode,
                    is_native = is_native,
                ))

        logger.debug(
            "VLAN memberships (sens inverse) : %d entrées sur %s.", len(memberships), client.ip
        )

    else:
        # Fallback : sens direct depuis allowed_vlans, mais limité aux VLANs <= 1000
        # pour éviter l'explosion quand le trunk autorise 1-4094
        logger.debug(
            "VLAN memberships : fallback sens direct sur %s (pas de bridge_to_if).", client.ip
        )
        for trunk in trunks:
            if not trunk.is_trunk or not trunk.allowed_vlans:
                continue
            allowed = _parse_allowed_vlans(trunk.allowed_vlans)
            for vid in sorted(allowed):
                if vid > 1000:
                    # Heuristique : au-delà de 1000 sans bridge_map on risque l'explosion
                    continue
                is_native = (vid == trunk.native_vlan)
                memberships.append(VlanMembership(
                    if_index  = trunk.if_index,
                    vlan_tag  = vid,
                    mode      = "Native" if is_native else "Tagged",
                    is_native = is_native,
                ))

    # ── Ports access → VLAN Untagged via PVID ──
    pvid_data = _walk(client, _DOT1Q_PVID)
    for idx, pvid_raw in pvid_data.items():
        if not idx.isdigit():
            continue
        if_index = int(idx)
        if if_index in trunk_if_indexes:
            continue
        try:
            vlan_tag = int(pvid_raw)
            if 1 <= vlan_tag <= 4094:
                memberships.append(VlanMembership(
                    if_index  = if_index,
                    vlan_tag  = vlan_tag,
                    mode      = "Untagged",
                    is_native = False,
                ))
        except ValueError:
            pass

    # Dédoublonner sur (if_index, vlan_tag)
    seen: set[tuple] = set()
    unique: list[VlanMembership] = []
    for m in memberships:
        key = (m.if_index, m.vlan_tag)
        if key not in seen:
            seen.add(key)
            unique.append(m)

    logger.debug(
        "VLAN memberships total : %d entrées uniques sur %s.", len(unique), client.ip
    )
    return memberships


def check_trunks(client: SnmpClient) -> TrunkCheckResult:
    """
    Collecte les trunks 802.1Q et les appartenances VLAN par interface.

    Args:
        client: Client SNMP configuré.

    Returns:
        :class:`TrunkCheckResult` avec trunks et memberships VLAN.
    """
    result = TrunkCheckResult()

    trunks = _collect_cisco_trunks(client)
    result.trunks = trunks
    result.vlans  = _collect_vlan_memberships(client, trunks)

    return result