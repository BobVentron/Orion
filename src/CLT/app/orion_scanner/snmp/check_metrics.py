"""
Check métriques SNMP — CPU, RAM, compteurs interfaces.

Sources par ordre de priorité
-------------------------------
CPU :
  1. HOST-RESOURCES-MIB hrProcessorLoad  (1.3.6.1.2.1.25.3.3.1.2)
     Standard, fonctionne sur Cisco IOS-XE, Juniper, Linux/net-snmp, HP...
  2. CISCO-PROCESS-MIB cpmCPUTotal5minRev (1.3.6.1.4.1.9.9.109.1.1.1.1.8)
     Cisco IOS classique (ancien)

RAM :
  1. HOST-RESOURCES-MIB hrStorageTable  (1.3.6.1.2.1.25.2.3.1)
     hrStorageType / hrStorageSize / hrStorageUsed
     Filtre sur hrStorageType = hrStorageRam (1.3.6.1.2.1.25.2.1.2)
  2. CISCO-MEMORY-POOL-MIB ciscoMemoryPool (1.3.6.1.4.1.9.9.48.1.1.1)
     ciscoMemoryPoolUsed / ciscoMemoryPoolFree

Interfaces (IF-MIB + IF-MIB extensions HC) :
  - ifHCInOctets    1.3.6.1.2.1.31.1.1.1.6   (64-bit, priorité)
  - ifHCOutOctets   1.3.6.1.2.1.31.1.1.1.10
  - ifHCInUcastPkts 1.3.6.1.2.1.31.1.1.1.7
  - ifHCOutUcastPkts 1.3.6.1.2.1.31.1.1.1.11
  - ifInNUcastPkts  1.3.6.1.2.1.2.2.1.12
  - ifOutNUcastPkts 1.3.6.1.2.1.2.2.1.13
  - ifInErrors      1.3.6.1.2.1.2.2.1.14
  - ifOutErrors     1.3.6.1.2.1.2.2.1.20
  - ifInDiscards    1.3.6.1.2.1.2.2.1.13  (overlap avec nucast sur certains)
  - ifOutDiscards   1.3.6.1.2.1.2.2.1.19
  - ifInUnknownProtos 1.3.6.1.2.1.2.2.1.15

Température (Cisco) :
  - CISCO-ENVMON-MIB ciscoEnvMonTemperatureValue (1.3.6.1.4.1.9.9.13.1.3.1.3)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from orion_scanner.snmp.client import SnmpClient, SnmpError
from orion_scanner.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# OIDs
# ---------------------------------------------------------------------------

# HOST-RESOURCES-MIB — CPU
_HR_PROCESSOR_LOAD     = "1.3.6.1.2.1.25.3.3.1.2"

# CISCO-PROCESS-MIB — CPU (fallback Cisco IOS classique)
_CISCO_CPU_5MIN        = "1.3.6.1.4.1.9.9.109.1.1.1.1.8"

# HOST-RESOURCES-MIB — RAM
_HR_STORAGE_TYPE       = "1.3.6.1.2.1.25.2.3.1.2"
_HR_STORAGE_SIZE       = "1.3.6.1.2.1.25.2.3.1.5"
_HR_STORAGE_USED       = "1.3.6.1.2.1.25.2.3.1.6"
_HR_STORAGE_UNITS      = "1.3.6.1.2.1.25.2.3.1.4"   # allocation units (bytes)
_HR_STORAGE_RAM_TYPE   = "1.3.6.1.2.1.25.2.1.2"    # OID du type RAM

# CISCO-MEMORY-POOL-MIB — RAM (fallback)
_CISCO_MEM_USED        = "1.3.6.1.4.1.9.9.48.1.1.1.5"
_CISCO_MEM_FREE        = "1.3.6.1.4.1.9.9.48.1.1.1.6"

# IF-MIB HC (64-bit — priorité)
_IF_HC_IN_OCTETS       = "1.3.6.1.2.1.31.1.1.1.6"
_IF_HC_OUT_OCTETS      = "1.3.6.1.2.1.31.1.1.1.10"
_IF_HC_IN_UCAST        = "1.3.6.1.2.1.31.1.1.1.7"
_IF_HC_OUT_UCAST       = "1.3.6.1.2.1.31.1.1.1.11"

# IF-MIB standard (32-bit — fallback)
_IF_IN_OCTETS          = "1.3.6.1.2.1.2.2.1.10"
_IF_OUT_OCTETS         = "1.3.6.1.2.1.2.2.1.16"
_IF_IN_UCAST           = "1.3.6.1.2.1.2.2.1.11"
_IF_OUT_UCAST          = "1.3.6.1.2.1.2.2.1.17"

# IF-MIB — counters communs
_IF_IN_NUCAST          = "1.3.6.1.2.1.2.2.1.12"
_IF_OUT_NUCAST         = "1.3.6.1.2.1.2.2.1.13"
_IF_IN_DISCARDS        = "1.3.6.1.2.1.2.2.1.13"
_IF_OUT_DISCARDS       = "1.3.6.1.2.1.2.2.1.19"
_IF_IN_ERRORS          = "1.3.6.1.2.1.2.2.1.14"
_IF_OUT_ERRORS         = "1.3.6.1.2.1.2.2.1.20"
_IF_IN_UNKNOWN_PROTOS  = "1.3.6.1.2.1.2.2.1.15"

# Température Cisco
_CISCO_TEMP_VALUE      = "1.3.6.1.4.1.9.9.13.1.3.1.3"


# ---------------------------------------------------------------------------
# Dataclasses résultat
# ---------------------------------------------------------------------------

@dataclass
class DeviceMetricsResult:
    """Métriques système du device."""
    cpu_load:     int | None = None   # % (0-100)
    ram_usage:    int | None = None   # % (0-100)
    ram_free:     int | None = None   # % (0-100)
    temp_celsius: int | None = None   # °C premier capteur


@dataclass
class InterfaceMetricsResult:
    """Compteurs bruts d'une interface."""
    if_index:         int
    in_octets:        int | None = None
    out_octets:       int | None = None
    in_ucast_pkts:    int | None = None
    out_ucast_pkts:   int | None = None
    in_nucast_pkts:   int | None = None
    out_nucast_pkts:  int | None = None
    in_errors:        int | None = None
    out_errors:       int | None = None
    in_discards:      int | None = None
    out_discards:     int | None = None
    in_unknown_protos: int | None = None


@dataclass
class MetricsCheckResult:
    """Résultat complet d'un check métriques sur un device."""
    device:     DeviceMetricsResult = field(default_factory=DeviceMetricsResult)
    interfaces: list[InterfaceMetricsResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _walk(client: SnmpClient, oid: str) -> dict[str, str]:
    """Walk une colonne OID, retourne {last_index: value}."""
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


def _to_int(v: str | None) -> int | None:
    if not v:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _pct(used: int | None, total: int | None) -> int | None:
    if used is None or total is None or total == 0:
        return None
    return min(100, int(used * 100 / total))


# ---------------------------------------------------------------------------
# CPU
# ---------------------------------------------------------------------------

def _collect_cpu_hr(client: SnmpClient) -> int | None:
    """HOST-RESOURCES-MIB hrProcessorLoad — moyenne sur tous les CPUs."""
    loads = _walk(client, _HR_PROCESSOR_LOAD)
    if not loads:
        return None
    values = [int(v) for v in loads.values() if v.isdigit()]
    if not values:
        return None
    avg = int(sum(values) / len(values))
    logger.debug("CPU (HR-MIB) %s : %d%%", client.ip, avg)
    return min(100, avg)


def _collect_cpu_cisco(client: SnmpClient) -> int | None:
    """CISCO-PROCESS-MIB cpmCPUTotal5minRev — fallback Cisco IOS."""
    data = _walk(client, _CISCO_CPU_5MIN)
    if not data:
        return None
    values = [int(v) for v in data.values() if v.isdigit()]
    if not values:
        return None
    avg = int(sum(values) / len(values))
    logger.debug("CPU (Cisco) %s : %d%%", client.ip, avg)
    return min(100, avg)


def collect_cpu(client: SnmpClient) -> int | None:
    """Collecte le taux de CPU, toutes sources confondues."""
    cpu = _collect_cpu_hr(client)
    if cpu is None:
        cpu = _collect_cpu_cisco(client)
    return cpu


# ---------------------------------------------------------------------------
# RAM
# ---------------------------------------------------------------------------

def _collect_ram_hr(client: SnmpClient) -> tuple[int | None, int | None]:
    """
    HOST-RESOURCES-MIB hrStorageTable.
    Retourne (ram_usage_pct, ram_free_pct).
    Cherche les entrées de type hrStorageRam.
    """
    types = _walk(client, _HR_STORAGE_TYPE)
    if not types:
        return None, None

    sizes = _walk(client, _HR_STORAGE_SIZE)
    useds = _walk(client, _HR_STORAGE_USED)
    units = _walk(client, _HR_STORAGE_UNITS)

    total_bytes = 0
    used_bytes  = 0

    for idx, stype in types.items():
        # hrStorageRam OID se termine par .2 dans hrStorageTypes
        if not stype.endswith(".2"):
            continue
        unit = _to_int(units.get(idx)) or 1
        size = (_to_int(sizes.get(idx)) or 0) * unit
        used = (_to_int(useds.get(idx)) or 0) * unit
        total_bytes += size
        used_bytes  += used

    if total_bytes == 0:
        return None, None

    usage_pct = min(100, int(used_bytes * 100 / total_bytes))
    free_pct  = 100 - usage_pct
    logger.debug("RAM (HR-MIB) %s : %d%% used", client.ip, usage_pct)
    return usage_pct, free_pct


def _collect_ram_cisco(client: SnmpClient) -> tuple[int | None, int | None]:
    """CISCO-MEMORY-POOL-MIB — fallback Cisco IOS."""
    used_data = _walk(client, _CISCO_MEM_USED)
    free_data = _walk(client, _CISCO_MEM_FREE)
    if not used_data or not free_data:
        return None, None

    total_used = sum(_to_int(v) or 0 for v in used_data.values())
    total_free = sum(_to_int(v) or 0 for v in free_data.values())
    total = total_used + total_free
    if total == 0:
        return None, None

    usage_pct = min(100, int(total_used * 100 / total))
    free_pct  = 100 - usage_pct
    logger.debug("RAM (Cisco) %s : %d%% used", client.ip, usage_pct)
    return usage_pct, free_pct


def collect_ram(client: SnmpClient) -> tuple[int | None, int | None]:
    """
    Collecte l'utilisation RAM.
    Retourne (usage_pct, free_pct).
    """
    usage, free = _collect_ram_hr(client)
    if usage is None:
        usage, free = _collect_ram_cisco(client)
    return usage, free


# ---------------------------------------------------------------------------
# Température
# ---------------------------------------------------------------------------

def collect_temperature(client: SnmpClient) -> int | None:
    """CISCO-ENVMON-MIB — premier capteur de température disponible."""
    data = _walk(client, _CISCO_TEMP_VALUE)
    if not data:
        return None
    values = [_to_int(v) for v in data.values() if _to_int(v) is not None]
    if not values:
        return None
    return values[0]  # Premier capteur (chassis principal)


# ---------------------------------------------------------------------------
# Compteurs interfaces
# ---------------------------------------------------------------------------

def collect_interface_metrics(client: SnmpClient) -> list[InterfaceMetricsResult]:
    """
    Collecte les compteurs bruts de toutes les interfaces.

    Priorité aux compteurs HC 64-bit (ifHCInOctets…) pour éviter le wrap
    sur les liens Gigabit/10G. Fallback sur les 32-bit si HC absent.
    """
    # HC counters (64-bit)
    hc_in_oct  = _walk(client, _IF_HC_IN_OCTETS)
    hc_out_oct = _walk(client, _IF_HC_OUT_OCTETS)
    hc_in_uc   = _walk(client, _IF_HC_IN_UCAST)
    hc_out_uc  = _walk(client, _IF_HC_OUT_UCAST)

    # 32-bit fallback
    in_oct  = _walk(client, _IF_IN_OCTETS)  if not hc_in_oct  else {}
    out_oct = _walk(client, _IF_OUT_OCTETS) if not hc_out_oct else {}
    in_uc   = _walk(client, _IF_IN_UCAST)   if not hc_in_uc   else {}
    out_uc  = _walk(client, _IF_OUT_UCAST)  if not hc_out_uc  else {}

    # Compteurs communs (pas de version HC)
    in_nucast  = _walk(client, _IF_IN_NUCAST)
    out_nucast = _walk(client, _IF_OUT_NUCAST)
    in_disc    = _walk(client, _IF_IN_DISCARDS)
    out_disc   = _walk(client, _IF_OUT_DISCARDS)
    in_err     = _walk(client, _IF_IN_ERRORS)
    out_err    = _walk(client, _IF_OUT_ERRORS)
    in_unk     = _walk(client, _IF_IN_UNKNOWN_PROTOS)

    # Union des ifIndex connus
    all_indexes = (
        set(hc_in_oct or in_oct) |
        set(hc_out_oct or out_oct) |
        set(in_err) | set(out_err)
    )

    results: list[InterfaceMetricsResult] = []
    for idx in sorted(all_indexes, key=lambda x: int(x) if x.isdigit() else 0):
        if not idx.isdigit():
            continue
        results.append(InterfaceMetricsResult(
            if_index        = int(idx),
            in_octets       = _to_int((hc_in_oct or in_oct).get(idx)),
            out_octets      = _to_int((hc_out_oct or out_oct).get(idx)),
            in_ucast_pkts   = _to_int((hc_in_uc or in_uc).get(idx)),
            out_ucast_pkts  = _to_int((hc_out_uc or out_uc).get(idx)),
            in_nucast_pkts  = _to_int(in_nucast.get(idx)),
            out_nucast_pkts = _to_int(out_nucast.get(idx)),
            in_errors       = _to_int(in_err.get(idx)),
            out_errors      = _to_int(out_err.get(idx)),
            in_discards     = _to_int(in_disc.get(idx)),
            out_discards    = _to_int(out_disc.get(idx)),
            in_unknown_protos = _to_int(in_unk.get(idx)),
        ))

    logger.debug(
        "Interface metrics : %d interfaces sur %s (HC=%s)",
        len(results), client.ip, bool(hc_in_oct),
    )
    return results


# ---------------------------------------------------------------------------
# Point d'entrée principal
# ---------------------------------------------------------------------------

def collect_metrics(client: SnmpClient) -> MetricsCheckResult:
    """
    Collecte toutes les métriques d'un équipement en un seul appel.

    Args:
        client: Client SNMP configuré et ayant passé le probe.

    Returns:
        :class:`MetricsCheckResult` avec device + interfaces.
    """
    result = MetricsCheckResult()

    cpu = collect_cpu(client)
    ram_usage, ram_free = collect_ram(client)
    temp = collect_temperature(client)

    result.device = DeviceMetricsResult(
        cpu_load     = cpu,
        ram_usage    = ram_usage,
        ram_free     = ram_free,
        temp_celsius = temp,
    )

    result.interfaces = collect_interface_metrics(client)

    logger.debug(
        "Metrics %s — cpu=%s%% ram=%s%% temp=%s°C ifaces=%d",
        client.ip,
        cpu, ram_usage, temp,
        len(result.interfaces),
    )
    return result
