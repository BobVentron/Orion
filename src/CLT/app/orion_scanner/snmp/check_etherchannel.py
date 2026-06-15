"""
Check EtherChannel / LACP — collecteur IEEE 802.3ad.

OIDs IEEE 802.3ad LAG-MIB (dot3adAggPortTable = 1.3.6.1.2.1.43.1.2.1)
-----------------------------------------------------------------------
  Index   = ifIndex du port membre (physique)
  Col 4   dot3adAggPortActorOperKey        — numéro du groupe EtherChannel
  Col 12  dot3adAggPortPartnerOperSystemID — MAC du switch partenaire (oper)
  Col 13  dot3adAggPortAttachedAggID       — ifIndex de l'interface Po locale
  Col 17  dot3adAggPortPartnerOperPortNum  — ifIndex du port côté partenaire

Logique de création des network_links
--------------------------------------
Pour un EtherChannel Gi1<->Gi1, Gi2<->Gi2, Gi3<->Gi3 entre SW-A et SW-B :

  SW-A voit :
    membre Gi1 (ifIdx 1)  -> Po1 (ifIdx 10) -> partenaire MAC=SW-B, portNum=1
    membre Gi2 (ifIdx 2)  -> Po1 (ifIdx 10) -> partenaire MAC=SW-B, portNum=2
    membre Gi3 (ifIdx 3)  -> Po1 (ifIdx 10) -> partenaire MAC=SW-B, portNum=3

  On cree 3 network_links physiques :
    SW-A:Gi1 <-> SW-B:Gi1
    SW-A:Gi2 <-> SW-B:Gi2
    SW-A:Gi3 <-> SW-B:Gi3

  Normalisation src < dst -> pas de doublons quand SW-B est aussi scanne.
  On ne cree PAS de lien Po<->Po (virtuel, pas un cable physique).
"""

from __future__ import annotations

from dataclasses import dataclass

from orion_scanner.snmp.client import SnmpClient, SnmpError
from orion_scanner.utils.logger import get_logger

logger = get_logger(__name__)

_DOT3AD_AGG_PORT_TABLE  = "1.3.6.1.2.1.43.1.2.1"
_COL_ACTOR_OPER_KEY     = 4
_COL_PARTNER_OPER_SYSID = 12   # MAC partenaire (oper)
_COL_ATTACHED_AGG_ID    = 13   # ifIndex Po locale
_COL_PARTNER_PORT_NUM   = 17   # ifIndex port partenaire


@dataclass
class LagMemberEntry:
    member_if_index:      int
    agg_if_index:         int
    oper_key:             int | None
    partner_sys_id:       str | None
    partner_port_ifindex: int | None
    protocol:             str = "LACP"


def _walk(client: SnmpClient, oid: str) -> dict[str, str]:
    try:
        rows = client.walk(oid)
    except SnmpError as exc:
        logger.debug("Walk %s sur %s : %s", oid, client.ip, exc)
        return {}
    result: dict[str, str] = {}
    for full_oid, value in rows:
        if not value or value.lower().startswith("no such"):
            continue
        idx = full_oid.rsplit(".", 1)[-1]
        result[idx] = value.strip()
    return result


def check_etherchannel(client: SnmpClient) -> list[LagMemberEntry]:
    base = _DOT3AD_AGG_PORT_TABLE

    attached = _walk(client, f"{base}.{_COL_ATTACHED_AGG_ID}")
    if not attached:
        logger.debug("EtherChannel : LAG-MIB absent ou vide sur %s.", client.ip)
        return []

    oper_keys       = _walk(client, f"{base}.{_COL_ACTOR_OPER_KEY}")
    partner_sys_ids = _walk(client, f"{base}.{_COL_PARTNER_OPER_SYSID}")
    partner_ports   = _walk(client, f"{base}.{_COL_PARTNER_PORT_NUM}")

    results: list[LagMemberEntry] = []
    for member_idx_str, agg_idx_str in attached.items():
        if not member_idx_str.isdigit():
            continue
        try:
            agg_if_index    = int(agg_idx_str)
            member_if_index = int(member_idx_str)
        except ValueError:
            continue

        if agg_if_index == 0:
            continue

        partner_port_idx: int | None = None
        raw_port = partner_ports.get(member_idx_str, "")
        if raw_port and raw_port.isdigit():
            v = int(raw_port)
            if v > 0:
                partner_port_idx = v

        partner_sys_id = partner_sys_ids.get(member_idx_str)
        if partner_sys_id in (None, "", "0:0:0:0:0:0", "00:00:00:00:00:00"):
            partner_sys_id = None

        results.append(LagMemberEntry(
            member_if_index      = member_if_index,
            agg_if_index         = agg_if_index,
            oper_key             = int(oper_keys[member_idx_str]) if member_idx_str in oper_keys else None,
            partner_sys_id       = partner_sys_id,
            partner_port_ifindex = partner_port_idx,
            protocol             = "LACP",
        ))

    logger.debug(
        "EtherChannel : %d membres sur %s (%d avec portNum partenaire).",
        len(results), client.ip,
        sum(1 for r in results if r.partner_port_ifindex is not None),
    )
    return results