"""
Check HSRP / VRRP — collecteur redondance L3.

CISCO-HSRP-MIB (1.3.6.1.4.1.9.9.106)
---------------------------------------
cHsrpGrpTable = 1.3.6.1.4.1.9.9.106.1.2.1.1
  Index : ifIndex.groupNumber
  Col 3   cHsrpGrpPriority
  Col 4   cHsrpGrpPreempt         1=true
  Col 7   cHsrpGrpHelloTime       centisecondes
  Col 8   cHsrpGrpHoldTime        centisecondes
  Col 9   cHsrpGrpVirtualIpAddr   IP virtuelle (IpAddress SNMP)
  Col 13  cHsrpGrpStandbyState    1=initial 2=learn 3=listen 4=speak 5=standby 6=active

VRRP-MIB RFC 2787 (1.3.6.1.2.1.68)
--------------------------------------
vrrpOperTable = 1.3.6.1.2.1.68.1.3.1
  Index : ifIndex.vrid
  Col 3   vrrpOperVirtualIpAddr
  Col 5   vrrpOperPriority
  Col 7   vrrpOperPreemptMode     1=true
  Col 11  vrrpOperState           1=initialize 2=backup 3=master
"""

from __future__ import annotations

import re
import socket
import struct
from dataclasses import dataclass

from orion_scanner.snmp.client import SnmpClient, SnmpError
from orion_scanner.utils.logger import get_logger

logger = get_logger(__name__)

_HSRP_TABLE      = "1.3.6.1.4.1.9.9.106.1.2.1.1"
_HSRP_PRIORITY   = 3
_HSRP_PREEMPT    = 4
_HSRP_HELLO_TIME = 7
_HSRP_HOLD_TIME  = 8
_HSRP_VIRTUAL_IP    = 9
_HSRP_ACTIVE_ROUTER = 11   # cHsrpGrpActiveRouter — IP du routeur actif
_HSRP_STATE         = 13

_VRRP_TABLE      = "1.3.6.1.2.1.68.1.3.1"
_VRRP_VIRTUAL_IP = 3
_VRRP_PRIORITY   = 5
_VRRP_PREEMPT    = 7
_VRRP_STATE      = 11

_HSRP_STATE_MAP = {
    "1": "Init", "2": "Learn", "3": "Listen",
    "4": "Init", "5": "Standby", "6": "Active",
}
_VRRP_STATE_MAP = {
    "1": "Init", "2": "Backup", "3": "Master",
}

_IP_RE = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class RedundancyEntry:
    if_index:   int
    group_id:   int
    protocol:   str
    virtual_ip: str | None
    state:      str
    priority:   int | None
    preempt:          bool = False
    hello_time:       int | None = None   # secondes
    hold_time:        int | None = None   # secondes
    active_router_ip: str | None = None   # IP du routeur actif (résolu en UUID dans le writer)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _walk_col(client: SnmpClient, table_base: str, col: int) -> dict[str, str]:
    """
    Walk une seule colonne de table SNMP.

    Construit l'OID complet = table_base.col, puis extrait le suffix
    d'index (= tout ce qui suit table_base.col.) pour chaque ligne.

    Retourne {index_suffix: valeur_brute}.
    L'index_suffix pour HSRP est "ifIndex.groupNumber", ex: "3.10".

    Note sur pysnmp-lextudio 6.x : les OIDs retournés peuvent parfois
    inclure ou omettre le point final — on normalise explicitement.
    """
    col_oid = f"{table_base}.{col}"
    prefix  = col_oid + "."
    try:
        rows = client.walk(col_oid)
    except SnmpError as exc:
        logger.debug("Walk %s : %s", col_oid, exc)
        return {}

    result: dict[str, str] = {}
    for oid, value in rows:
        if not value or value.lower().startswith("no such"):
            continue

        # Normaliser : certains implémentations retournent l'OID
        # avec un préfixe légèrement différent (ex: sans le numéro
        # d'entrée de table). On cherche le prefix exact d'abord,
        # puis on tente de trouver le suffix à partir de table_base.col.
        if oid.startswith(prefix):
            idx = oid[len(prefix):]
        elif f".{col}." in oid:
            # Extraire tout ce qui suit ".col." — robuste aux variations
            idx = oid.split(f".{col}.", 1)[-1]
        else:
            # Dernier recours : ignorer cette ligne plutôt que de
            # prendre un mauvais suffix et corrompre les associations
            logger.debug("HSRP walk: OID inattendu ignoré: %s", oid)
            continue

        result[idx] = value.strip()
    return result


def _parse_snmp_ip(raw: str) -> str | None:
    """
    Normalise une IpAddress SNMP en "x.x.x.x".

    Formats possibles retournés par pysnmp-lextudio 6.x :
      "192.168.10.2"   → notation pointée standard
      "0xc0a80a02"     → hexadécimal
      "3232238082"     → entier décimal 32-bit
    Valeurs à rejeter : "0.0.0.0", "", nombres < 0x01000000 (ex: "3000")
    """
    if not raw or raw in ("0.0.0.0", ""):
        return None

    # Notation pointée standard
    m = _IP_RE.match(raw)
    if m:
        octets = [int(g) for g in m.groups()]
        if all(0 <= o <= 255 for o in octets) and octets[0] != 0:
            return raw
        return None

    # Hexadécimal "0x..."
    cleaned = raw.replace("0x", "").replace(" ", "").strip()
    if len(cleaned) == 8 and all(c in "0123456789abcdefABCDEF" for c in cleaned):
        try:
            n = int(cleaned, 16)
            if n >= 0x01000000:   # Rejette les valeurs type "0x00000BB8" = 3000
                packed = struct.pack(">I", n)
                return socket.inet_ntoa(packed)
        except Exception:
            pass
        return None

    # Entier décimal pur
    if raw.isdigit():
        n = int(raw)
        # Une IPv4 valide en décimal = min 0x01000000 = 16777216
        if n >= 16_777_216:
            try:
                packed = struct.pack(">I", n)
                return socket.inet_ntoa(packed)
            except Exception:
                pass
        # Valeur trop petite pour être une IP (ex: "3000") → rejeté
        return None

    return None


def _to_int(v: str | None) -> int | None:
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# HSRP
# ---------------------------------------------------------------------------

def _collect_hsrp(client: SnmpClient) -> list[RedundancyEntry]:
    base = _HSRP_TABLE

    states = _walk_col(client, base, _HSRP_STATE)

    # Fallback : certains equipements peuplent les VIPs mais pas les states
    # On tente quand meme si on a des VIPs
    vips = _walk_col(client, base, _HSRP_VIRTUAL_IP)

    if not states and not vips:
        logger.debug("HSRP : aucune donnee sur %s (MIB absente ou HSRP non configure).", client.ip)
        return []

    if not states:
        logger.debug(
            "HSRP : states vide mais %d VIP(s) trouves sur %s — "
            "suffixes states=%s vips=%s",
            len(vips), client.ip,
            list(states.keys())[:3], list(vips.keys())[:3],
        )
        # Construire des entrees avec etat inconnu depuis les VIPs
        states = {k: "0" for k in vips}  # 0 = etat inconnu -> Init

    priorities  = _walk_col(client, base, _HSRP_PRIORITY)
    preempts    = _walk_col(client, base, _HSRP_PREEMPT)
    hello_times    = _walk_col(client, base, _HSRP_HELLO_TIME)
    hold_times     = _walk_col(client, base, _HSRP_HOLD_TIME)
    active_routers = _walk_col(client, base, _HSRP_ACTIVE_ROUTER)

    logger.debug(
        "HSRP raw — states=%s vips=%s priorities=%s",
        dict(list(states.items())[:3]),
        dict(list(vips.items())[:3]),
        dict(list(priorities.items())[:3]),
    )

    results: list[RedundancyEntry] = []
    for suffix, state_raw in states.items():
        parts = suffix.split(".")
        if len(parts) < 2:
            continue
        try:
            if_index = int(parts[0])
            group_id = int(parts[1])
        except ValueError:
            continue

        vip_raw    = vips.get(suffix, "")
        virtual_ip = _parse_snmp_ip(vip_raw)

        hello_cs = _to_int(hello_times.get(suffix))
        hold_cs  = _to_int(hold_times.get(suffix))
        hello_s  = (hello_cs // 100) if hello_cs is not None else None
        hold_s   = (hold_cs  // 100) if hold_cs  is not None else None

        # Tronquer les valeurs inconnues pour respecter VARCHAR(20)
        # et logger pour debug
        state_str = _HSRP_STATE_MAP.get(state_raw)
        if state_str is None:
            logger.debug(
                "HSRP if=%d grp=%d — état inconnu raw='%s' (attendu 1-6)",
                if_index, group_id, state_raw,
            )
            state_str = "Init"   # Valeur sûre par défaut

        if virtual_ip is None and vip_raw:
            logger.debug(
                "HSRP if=%d grp=%d — vip_raw='%s' rejeté (non-IP valide)",
                if_index, group_id, vip_raw,
            )

        active_ip = _parse_snmp_ip(active_routers.get(suffix, ""))

        results.append(RedundancyEntry(
            if_index          = if_index,
            group_id          = group_id,
            protocol          = "HSRP",
            virtual_ip        = virtual_ip,
            state             = state_str,
            priority          = _to_int(priorities.get(suffix)),
            preempt           = preempts.get(suffix) == "1",
            hello_time        = hello_s,
            hold_time         = hold_s,
            active_router_ip  = active_ip,
        ))

    logger.debug("HSRP : %d groupes sur %s.", len(results), client.ip)
    return results


# ---------------------------------------------------------------------------
# VRRP
# ---------------------------------------------------------------------------

def _collect_vrrp(client: SnmpClient) -> list[RedundancyEntry]:
    base = _VRRP_TABLE

    states = _walk_col(client, base, _VRRP_STATE)
    if not states:
        return []

    priorities = _walk_col(client, base, _VRRP_PRIORITY)
    preempts   = _walk_col(client, base, _VRRP_PREEMPT)
    vips       = _walk_col(client, base, _VRRP_VIRTUAL_IP)

    results: list[RedundancyEntry] = []
    for suffix, state_raw in states.items():
        parts = suffix.split(".")
        if len(parts) < 2:
            continue
        try:
            if_index = int(parts[0])
            group_id = int(parts[1])
        except ValueError:
            continue

        virtual_ip = _parse_snmp_ip(vips.get(suffix, ""))
        state_str = _VRRP_STATE_MAP.get(state_raw)
        if state_str is None:
            logger.debug("VRRP if=%d grp=%d — état inconnu raw='%s'", if_index, group_id, state_raw)
            state_str = "Init"

        results.append(RedundancyEntry(
            if_index   = if_index,
            group_id   = group_id,
            protocol   = "VRRP",
            virtual_ip = virtual_ip,
            state      = state_str,
            priority   = _to_int(priorities.get(suffix)),
            preempt    = preempts.get(suffix) == "1",
        ))

    logger.debug("VRRP : %d groupes sur %s.", len(results), client.ip)
    return results


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def check_hsrp_vrrp(client: SnmpClient) -> list[RedundancyEntry]:
    results: list[RedundancyEntry] = []
    results.extend(_collect_hsrp(client))
    results.extend(_collect_vrrp(client))
    if results:
        logger.debug(
            "HSRP/VRRP total : %d groupe(s) sur %s (hsrp=%d vrrp=%d).",
            len(results), client.ip,
            sum(1 for r in results if r.protocol == "HSRP"),
            sum(1 for r in results if r.protocol == "VRRP"),
        )
    return results