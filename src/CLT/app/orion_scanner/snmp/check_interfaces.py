"""
Check interfaces — collecteur léger de statut d'interfaces.

Contrairement à collect_interfaces() qui fait un walk complet (IF-MIB + ifXTable),
ce module ne récupère que les colonnes volatiles qui changent fréquemment :
- ifAdminStatus (1.3.6.1.2.1.2.2.1.7)
- ifOperStatus  (1.3.6.1.2.1.2.2.1.8)
- ifHighSpeed   (1.3.6.1.2.1.31.1.1.1.15) — débit négocié courant

L'objectif est d'être aussi léger que possible pour des checks toutes les 30s-5min
sans surcharger les équipements.
"""

from __future__ import annotations

from orion_scanner.models import IfAdminStatus, IfOperStatus, InterfaceStatusCheck
from orion_scanner.snmp.client import SnmpClient, SnmpError
from orion_scanner.utils.logger import get_logger

logger = get_logger(__name__)

_OID_IF_ADMIN_STATUS = "1.3.6.1.2.1.2.2.1.7"
_OID_IF_OPER_STATUS  = "1.3.6.1.2.1.2.2.1.8"
_OID_IF_HIGH_SPEED   = "1.3.6.1.2.1.31.1.1.1.15"

_ADMIN_MAP = {"1": IfAdminStatus.UP, "2": IfAdminStatus.DOWN}
_OPER_MAP  = {"1": IfOperStatus.UP,  "2": IfOperStatus.DOWN}


def _walk(client: SnmpClient, oid: str) -> dict[str, str]:
    """Walk une colonne, retourne {ifIndex: value}."""
    try:
        rows = client.walk(oid)
    except SnmpError as exc:
        logger.debug("Walk %s sur %s échoué: %s", oid, client.ip, exc)
        return {}
    result: dict[str, str] = {}
    for full_oid, value in rows:
        if value.lower().startswith("no such"):
            continue
        idx = full_oid.rsplit(".", 1)[-1]
        result[idx] = value.strip()
    return result


def check_interfaces(client: SnmpClient) -> list[InterfaceStatusCheck]:
    """
    Collecte le statut courant de toutes les interfaces.

    Rapide : 3 walks seulement (admin_status, oper_status, high_speed).

    Args:
        client: Client SNMP configuré.

    Returns:
        Liste de :class:`~orion_scanner.models.InterfaceStatusCheck`,
        une entrée par ifIndex présent.
    """
    admin_statuses = _walk(client, _OID_IF_ADMIN_STATUS)
    if not admin_statuses:
        logger.debug("check_interfaces : aucune donnée sur %s.", client.ip)
        return []

    oper_statuses = _walk(client, _OID_IF_OPER_STATUS)
    high_speeds   = _walk(client, _OID_IF_HIGH_SPEED)

    results: list[InterfaceStatusCheck] = []
    for idx, admin_raw in admin_statuses.items():
        if not idx.isdigit():
            continue

        raw_speed = high_speeds.get(idx)
        speed_bps: int | None = None
        if raw_speed and raw_speed.isdigit():
            speed_bps = int(raw_speed) * 1_000_000  # Mbps → bps

        results.append(InterfaceStatusCheck(
            if_index=int(idx),
            admin_status=_ADMIN_MAP.get(admin_raw),
            oper_status=_OPER_MAP.get(oper_statuses.get(idx, ""), None),
            speed_bps=speed_bps,
        ))

    logger.debug(
        "check_interfaces : %d interfaces sur %s.", len(results), client.ip
    )
    return results
