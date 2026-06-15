"""
Check ARP table — collecteur via IP-MIB ipNetToMediaTable.

OIDs IP-MIB (RFC 1213 / RFC 4293)
-----------------------------------
ipNetToMediaTable = 1.3.6.1.2.1.4.22.1
  Index : ifIndex.ip_octet1.ip_octet2.ip_octet3.ip_octet4
  Col 1  ipNetToMediaIfIndex     — ifIndex
  Col 2  ipNetToMediaPhysAddress — MAC (OCTET STRING)
  Col 3  ipNetToMediaNetAddress  — IP (dans l'index)
  Col 4  ipNetToMediaType        — 1=other 2=invalid 3=dynamic 4=static

Fallback : ipNetToPhysicalTable (RFC 4293, IPv6 compatible)
  1.3.6.1.2.1.4.35.1
  Plus verbeux, même logique.

Note : on ne garde que les entrées dynamic (3) et static (4).
Les entrées invalid (2) sont ignorées.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from orion_scanner.snmp.client import SnmpClient, SnmpError
from orion_scanner.utils.logger import get_logger

logger = get_logger(__name__)

_IP_NET_TO_MEDIA     = "1.3.6.1.2.1.4.22.1"
_COL_PHYS_ADDRESS    = 2   # MAC
_COL_TYPE            = 4   # 1=other 2=invalid 3=dynamic 4=static

_TYPE_MAP = {"3": "Dynamic", "4": "Static"}


@dataclass
class ArpEntry:
    """Une entrée de la table ARP."""
    if_index:    int
    ip_address:  str
    mac_address: str
    entry_type:  str = "Dynamic"


def _normalize_mac(raw: str) -> str | None:
    """Normalise une MAC SNMP en xx:xx:xx:xx:xx:xx."""
    cleaned = re.sub(r"[:\-\.\s]", "", raw.lower().replace("0x", ""))
    if len(cleaned) == 12 and all(c in "0123456789abcdef" for c in cleaned):
        return ":".join(cleaned[i:i+2] for i in range(0, 12, 2))
    return None


def _walk(client: SnmpClient, oid: str) -> list[tuple[str, str]]:
    try:
        return client.walk(oid)
    except SnmpError as exc:
        logger.debug("Walk %s sur %s : %s", oid, client.ip, exc)
        return []


def check_arp(client: SnmpClient) -> list[ArpEntry]:
    """
    Collecte la table ARP via ipNetToMediaTable.

    Retourne les entrées Dynamic et Static uniquement.
    L'IP est extraite du suffix OID (ifIndex.a.b.c.d).

    Args:
        client: Client SNMP configuré.

    Returns:
        Liste de :class:`ArpEntry`. Vide si MIB absente.
    """
    base       = _IP_NET_TO_MEDIA
    phys_base  = f"{base}.{_COL_PHYS_ADDRESS}."
    type_base  = f"{base}.{_COL_TYPE}."

    phys_rows  = _walk(client, f"{base}.{_COL_PHYS_ADDRESS}")
    if not phys_rows:
        logger.debug("ARP : ipNetToMediaTable vide sur %s.", client.ip)
        return []

    type_map: dict[str, str] = {}
    for oid, val in _walk(client, f"{base}.{_COL_TYPE}"):
        if oid.startswith(type_base):
            suffix = oid[len(type_base):]
            type_map[suffix] = val.strip()

    results: list[ArpEntry] = []
    for oid, mac_raw in phys_rows:
        if not oid.startswith(phys_base):
            continue
        suffix = oid[len(phys_base):]   # "ifIndex.a.b.c.d"

        parts = suffix.split(".")
        if len(parts) < 5:
            continue

        try:
            if_index = int(parts[0])
        except ValueError:
            continue

        ip_parts = parts[1:5]
        try:
            ip = ".".join(str(int(p)) for p in ip_parts)
        except ValueError:
            continue

        # Filtrer les IPs invalides
        if ip in ("0.0.0.0", "255.255.255.255") or ip.startswith("127."):
            continue

        # Type : garder dynamic (3) et static (4) seulement
        entry_type_raw = type_map.get(suffix, "3")
        if entry_type_raw == "2":   # invalid
            continue
        entry_type = _TYPE_MAP.get(entry_type_raw, "Dynamic")

        mac = _normalize_mac(mac_raw)
        if not mac:
            logger.debug("ARP: MAC invalide '%s' pour %s, ignorée.", mac_raw, ip)
            continue

        results.append(ArpEntry(
            if_index   = if_index,
            ip_address = ip,
            mac_address = mac,
            entry_type = entry_type,
        ))

    logger.debug("ARP : %d entrées sur %s.", len(results), client.ip)
    return results