"""
MIB-II System group collector (RFC 1213 / SNMPv2-MIB).

OIDs collected
--------------
- sysDescr      1.3.6.1.2.1.1.1.0
- sysObjectID   1.3.6.1.2.1.1.2.0
- sysUpTime     1.3.6.1.2.1.1.3.0
- sysContact    1.3.6.1.2.1.1.4.0
- sysName       1.3.6.1.2.1.1.5.0
- sysLocation   1.3.6.1.2.1.1.6.0
"""

from orion_scanner.models import SystemInfo
from orion_scanner.snmp.client import SnmpClient, SnmpError
from orion_scanner.utils.logger import get_logger

logger = get_logger(__name__)

# OID constants
_OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"
_OID_SYS_OBJECT_ID = "1.3.6.1.2.1.1.2.0"
_OID_SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
_OID_SYS_CONTACT = "1.3.6.1.2.1.1.4.0"
_OID_SYS_NAME = "1.3.6.1.2.1.1.5.0"
_OID_SYS_LOCATION = "1.3.6.1.2.1.1.6.0"

_ALL_SYSTEM_OIDS = (
    _OID_SYS_DESCR,
    _OID_SYS_OBJECT_ID,
    _OID_SYS_UPTIME,
    _OID_SYS_CONTACT,
    _OID_SYS_NAME,
    _OID_SYS_LOCATION,
)


def collect_system(client: SnmpClient) -> SystemInfo | None:
    """
    Fetch the MIB-II System group from *client*'s target host.

    Returns a populated :class:`~orion_scanner.models.SystemInfo` on success,
    or ``None`` if the host is unreachable / SNMP is not available.

    Args:
        client: A configured :class:`~orion_scanner.snmp.client.SnmpClient`.

    Returns:
        :class:`~orion_scanner.models.SystemInfo` or ``None``.
    """
    try:
        result = client.get(*_ALL_SYSTEM_OIDS)
    except SnmpError as exc:
        logger.debug("System collection failed for %s: %s", client.ip, exc)
        return None

    def _get(oid: str) -> str | None:
        val = result.get(oid)
        # pysnmp returns 'No Such Object' / 'No Such Instance' as strings
        if val and not val.lower().startswith("no such"):
            return val.strip()
        return None

    uptime_raw = _get(_OID_SYS_UPTIME)
    uptime_cs: int | None = None
    if uptime_raw is not None:
        try:
            # pysnmp renders uptime as a string like "12:34:56.78" or raw ticks
            uptime_cs = int(uptime_raw)
        except ValueError:
            uptime_cs = None  # will parse the formatted string if needed

    info = SystemInfo(
        ip=client.ip,
        sys_name=_get(_OID_SYS_NAME),
        sys_descr=_get(_OID_SYS_DESCR),
        sys_object_id=_get(_OID_SYS_OBJECT_ID),
        sys_location=_get(_OID_SYS_LOCATION),
        sys_contact=_get(_OID_SYS_CONTACT),
        sys_uptime_centiseconds=uptime_cs,
    )

    logger.debug(
        "System info collected for %s  name=%s  oid=%s",
        client.ip,
        info.sys_name,
        info.sys_object_id,
    )
    return info
