"""
Orion CLI — interface en ligne de commande.

    python -m orion_scanner.cli <commande> [options]
    python -m orion_scanner.cli --help
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from xml.dom import minidom

from sqlalchemy import select

from orion_scanner.db.engine import check_connection, get_session_factory
from orion_scanner.db.schema import (
    AuthCli, AuthProfile, AuthSnmp,
    Device, DeviceCategory, DeviceFamily, DeviceModel,
    DeviceStatus, Firmware, Interface, IpAddress, IpInterfaceMap,
    Location, NetworkLink, ScanNetwork, ScanProfile,
)
from orion_scanner.utils.logger import get_logger
from orion_scanner.utils.network import validate_cidr

logger = get_logger("orion_cli")


# ---------------------------------------------------------------------------
# Helpers affichage / saisie
# ---------------------------------------------------------------------------

def _sep(char: str = "─", width: int = 60) -> None:
    print(char * width)

def _header(title: str) -> None:
    _sep(); print(f"  {title}"); _sep()

def _ok(msg: str) -> None:
    print(f"  ✓  {msg}")

def _err(msg: str) -> None:
    print(f"  ✗  {msg}", file=sys.stderr)

def _prompt(label: str, default: str | None = None, secret: bool = False) -> str:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        val = (getpass.getpass if secret else input)(f"  {label}{suffix}: ").strip()
        if val:
            return val
        if default is not None:
            return default
        print("    Ce champ est obligatoire.")

def _prompt_int(label: str, default: int, min_val: int = 0, max_val: int = 99999) -> int:
    while True:
        raw = _prompt(label, str(default))
        if raw.lstrip('-').isdigit() and min_val <= int(raw) <= max_val:
            return int(raw)
        print(f"    Entrez un entier entre {min_val} et {max_val}.")

def _prompt_choice(label: str, choices: list[str], default: str) -> str:
    print(f"\n  {label}")
    for i, c in enumerate(choices, 1):
        print(f"    {i}) {c}{' (défaut)' if c == default else ''}")
    while True:
        raw = _prompt("Choix", str(choices.index(default) + 1))
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1]
        print(f"    Entrez un numéro entre 1 et {len(choices)}.")

def _get_session():
    if not check_connection():
        _err("Base de données inaccessible. Vérifiez DATABASE_URL.")
        sys.exit(1)
    return get_session_factory()


# ---------------------------------------------------------------------------
# profile list
# ---------------------------------------------------------------------------

def cmd_profile_list(_args: argparse.Namespace) -> None:
    factory = _get_session()
    with factory() as session:
        profiles = session.scalars(select(AuthProfile)).all()
    if not profiles:
        print("  Aucun profil d'authentification configuré.")
        return
    _header("Profils d'authentification")
    fmt = "  {:<4}  {:<30}  {:<20}  {:<20}"
    print(fmt.format("ID", "Nom", "SNMP", "CLI"))
    _sep()
    for p in profiles:
        print(fmt.format(
            p.id, p.name,
            p.snmp.name if p.snmp else "—",
            p.cli.name  if p.cli  else "—",
        ))


# ---------------------------------------------------------------------------
# profile create
# ---------------------------------------------------------------------------

def cmd_profile_create(_args: argparse.Namespace) -> None:
    _header("Création d'un profil d'authentification")
    factory = _get_session()
    with factory() as session:
        profile_name = _prompt("Nom du profil")

        print("\n  ── Configuration SNMP ──────────────────────────────")
        snmp_name    = _prompt("Nom de cette config SNMP", profile_name + "-snmp")
        snmp_version = _prompt_choice("Version SNMP", ["v1", "v2c", "v3"], default="v2c")
        snmp_port    = _prompt_int("Port SNMP", 161, 1, 65535)
        snmp = AuthSnmp(name=snmp_name, version=snmp_version, port=snmp_port)

        if snmp_version in ("v1", "v2c"):
            snmp.community = _prompt("Community string", secret=True)
        else:
            snmp.v3_user  = _prompt("Nom d'utilisateur (Security Name)")
            snmp.v3_level = _prompt_choice(
                "Niveau de sécurité",
                ["noAuthNoPriv", "authNoPriv", "authPriv"],
                default="authPriv",
            )
            if snmp.v3_level in ("authNoPriv", "authPriv"):
                snmp.v3_auth_proto = _prompt_choice(
                    "Protocole d'auth", ["MD5", "SHA", "SHA256", "SHA512"], default="SHA256"
                )
                snmp.v3_auth_pass = _prompt("Mot de passe auth", secret=True)
            if snmp.v3_level == "authPriv":
                snmp.v3_priv_proto = _prompt_choice(
                    "Protocole de chiffrement", ["DES", "AES", "AES128", "AES256"], default="AES256"
                )
                snmp.v3_priv_pass = _prompt("Mot de passe chiffrement", secret=True)

        session.add(snmp)
        session.flush()

        cli_id = None
        if _prompt("\n  Ajouter une config CLI (SSH/Telnet) ? (oui/non)", "non").lower() in ("oui","o","yes","y"):
            cli = AuthCli(
                name=_prompt("Nom de cette config CLI", profile_name + "-cli"),
                username=_prompt("Nom d'utilisateur"),
                password=_prompt("Mot de passe", secret=True),
                protocol_pref=_prompt_choice("Protocole", ["SSH", "Telnet"], default="SSH"),
                port=_prompt_int("Port", 22, 1, 65535),
            )
            session.add(cli)
            session.flush()
            cli_id = cli.id

        profile = AuthProfile(name=profile_name, snmp_id=snmp.id, cli_id=cli_id)
        session.add(profile)
        session.commit()
        profile_id = profile.id

    _ok(f"Profil '{profile_name}' créé (id={profile_id}).")


# ---------------------------------------------------------------------------
# profile delete
# ---------------------------------------------------------------------------

def cmd_profile_delete(args: argparse.Namespace) -> None:
    factory = _get_session()
    with factory() as session:
        profile = session.get(AuthProfile, args.id)
        if profile is None:
            _err(f"Profil id={args.id} introuvable."); sys.exit(1)
        if _prompt(f"Supprimer '{profile.name}' (id={profile.id}) ? (oui/non)", "non").lower() not in ("oui","o","yes","y"):
            print("  Annulé."); return
        session.delete(profile)
        session.commit()
    _ok(f"Profil id={args.id} supprimé.")


# ---------------------------------------------------------------------------
# scan-profile list
# ---------------------------------------------------------------------------

def cmd_scan_profile_list(_args: argparse.Namespace) -> None:
    factory = _get_session()
    with factory() as session:
        profiles = session.scalars(select(ScanProfile)).all()
    if not profiles:
        print("  Aucun profil de scan configuré."); return
    _header("Profils de scan")
    fmt = "  {:<4}  {:<25}  {:<18}  {:<10}  {:<8}  {:<6}"
    print(fmt.format("ID", "Nom", "Type", "Timeout", "Threads", "Actif"))
    _sep()
    for p in profiles:
        print(fmt.format(p.id, p.name, p.type, f"{p.timeout_ms}ms", str(p.concurrency_threads), "✓" if p.is_enabled else "✗"))


# ---------------------------------------------------------------------------
# scan-profile create
# ---------------------------------------------------------------------------

def cmd_scan_profile_create(_args: argparse.Namespace) -> None:
    _header("Création d'un profil de scan")
    factory = _get_session()
    with factory() as session:
        name      = _prompt("Nom du profil")
        scan_type = _prompt_choice(
            "Type de scan",
            ["SNMP_Discovery", "ICMP_Ping", "LLDP_Topology", "Port_Scan"],
            default="SNMP_Discovery",
        )
        timeout_ms  = _prompt_int("Timeout par hôte (ms)", 2000, 100, 30000)
        retry_count = _prompt_int("Tentatives en cas de timeout", 1, 0, 5)
        threads     = _prompt_int("Threads simultanés", 20, 1, 100)

        profile = ScanProfile(
            name=name,
            type=scan_type,
            timeout_ms=timeout_ms,
            retry_count=retry_count,
            concurrency_threads=threads,
            is_enabled=True,
        )
        session.add(profile)
        session.commit()
        profile_id = profile.id

    _ok(f"Profil de scan '{name}' créé (id={profile_id}).")


# ---------------------------------------------------------------------------
# network list
# ---------------------------------------------------------------------------

def cmd_network_list(_args: argparse.Namespace) -> None:
    factory = _get_session()
    with factory() as session:
        networks = session.scalars(select(ScanNetwork)).all()
    if not networks:
        print("  Aucun réseau configuré."); return
    _header("Réseaux configurés")
    fmt = "  {:<4}  {:<22}  {:<20}  {:<12}  {:<6}  {}"
    print(fmt.format("ID", "Subnet", "Profil auth", "Statut", "Hôtes", "Dernier scan"))
    _sep()
    for n in networks:
        last_at = "—"
        if n.last_scan_at:
            dt = n.last_scan_at
            if hasattr(dt, "astimezone"):
                dt = dt.astimezone(timezone.utc)
            last_at = dt.strftime("%Y-%m-%d %H:%M")
        auth_label = n.auth_profile.name if n.auth_profile else f"id={n.auth_profile_id}"
        print(fmt.format(n.id, str(n.subnet), auth_label, n.last_scan_status, str(n.last_hosts_found), last_at))


# ---------------------------------------------------------------------------
# network status
# ---------------------------------------------------------------------------

def cmd_network_status(_args: argparse.Namespace) -> None:
    factory = _get_session()
    with factory() as session:
        networks = session.scalars(select(ScanNetwork)).all()
    if not networks:
        print("  Aucun réseau configuré."); return
    _header("État des scans")
    icons = {"idle": "○", "running": "↻", "completed": "✓", "failed": "✗"}
    for n in networks:
        print(f"\n  {icons.get(n.last_scan_status,'?')}  [{n.id}] {n.subnet}")
        print(f"       Statut    : {n.last_scan_status}")
        if n.last_scan_at:
            print(f"       Dernier   : {n.last_scan_at}")
        if n.last_scan_duration is not None:
            print(f"       Durée     : {n.last_scan_duration}s")
        if n.last_hosts_found:
            print(f"       Hôtes     : {n.last_hosts_found}")
        if n.last_error:
            print(f"       Erreur    : {n.last_error}")
        if n.description:
            print(f"       Note      : {n.description}")

        interval_s = getattr(n, 'interval_seconds', 3600)
        if interval_s == 0:
            print(f"       Reschedule: scan unique (pas de répétition)")
        elif interval_s < 3600:
            print(f"       Intervalle: toutes les {interval_s}s ({interval_s//60}min)")
        else:
            print(f"       Intervalle: toutes les {interval_s//3600}h")

        next_at = getattr(n, 'next_scan_at', None)
        if next_at:
            dt = next_at
            if hasattr(dt, 'astimezone'):
                dt = dt.astimezone(timezone.utc)
            print(f"       Prochain  : {dt.strftime('%Y-%m-%d %H:%M UTC')}")
        else:
            print(f"       Prochain  : dès la prochaine passe du collecteur")


# ---------------------------------------------------------------------------
# network active
# ---------------------------------------------------------------------------

def cmd_network_active(_args: argparse.Namespace) -> None:
    """Affiche uniquement les scans actuellement en cours (status = running)."""
    factory = _get_session()
    with factory() as session:
        networks = session.scalars(
            select(ScanNetwork).where(ScanNetwork.last_scan_status == "running")
        ).all()
    if not networks:
        print("  Aucun scan en cours.")
        return
    _header(f"Scans en cours ({len(networks)})")
    for n in networks:
        started = "—"
        if n.last_scan_at:
            dt = n.last_scan_at
            if hasattr(dt, "astimezone"):
                dt = dt.astimezone(timezone.utc)
            started = dt.strftime("%H:%M:%S UTC")
        auth_label = n.auth_profile.name if n.auth_profile else f"id={n.auth_profile_id}"
        print(f"  ↻  [{n.id}] {n.subnet}  |  démarré: {started}  |  profil: {auth_label}")


# ---------------------------------------------------------------------------
# network add
# ---------------------------------------------------------------------------

def cmd_network_add(_args: argparse.Namespace) -> None:
    _header("Ajout d'un réseau à scanner")
    factory = _get_session()
    with factory() as session:

        # Subnet
        while True:
            raw_subnet = _prompt("Subnet (CIDR, ex: 192.168.1.0/24)")
            try:
                validate_cidr(raw_subnet); break
            except ValueError as exc:
                print(f"    {exc}")

        # IPs exclues
        raw_exclude = _prompt("IPs à exclure (virgule-séparées, vide = aucune)", "")
        exclude_list = [ip.strip() for ip in raw_exclude.split(",") if ip.strip()]
        exclude_json = json.dumps(exclude_list)

        # Profil d'auth
        auth_profiles = session.scalars(select(AuthProfile)).all()
        if not auth_profiles:
            _err("Aucun profil d'auth. Créez-en un avec 'profile create'."); sys.exit(1)
        print("\n  Profils d'authentification disponibles :")
        for p in auth_profiles:
            print(f"    {p.id}) {p.name}  (SNMP: {p.snmp.name if p.snmp else '—'})")
        auth_profile_id = _prompt_int("ID du profil d'auth", auth_profiles[0].id, 1, 99999)
        if not any(p.id == auth_profile_id for p in auth_profiles):
            _err(f"Profil id={auth_profile_id} introuvable."); sys.exit(1)

        # Profil de scan
        scan_profiles = session.scalars(select(ScanProfile)).all()
        if not scan_profiles:
            _err("Aucun profil de scan. Créez-en un avec 'scan-profile create'."); sys.exit(1)
        print("\n  Profils de scan disponibles :")
        for p in scan_profiles:
            print(f"    {p.id}) {p.name}  ({p.type}, {p.timeout_ms}ms, {p.concurrency_threads} threads)")
        scan_profile_id = _prompt_int("ID du profil de scan", scan_profiles[0].id, 1, 99999)
        if not any(p.id == scan_profile_id for p in scan_profiles):
            _err(f"Profil de scan id={scan_profile_id} introuvable."); sys.exit(1)

        # Intervalle de reschedule
        print("")
        print("  Intervalle entre deux scans (0 = scan unique, ne se répète jamais)")
        print("")
        print("  Intervalle entre deux scans (en secondes, 0 = scan unique)")
        print("  Exemples : 300=5min  3600=1h  86400=24h")
        interval_seconds = _prompt_int("Intervalle en secondes", 3600, 0, 604800)

        # Description
        description = _prompt("Description (optionnel)", "") or None

        network = ScanNetwork(
            subnet=raw_subnet,
            exclude_ips=exclude_json,
            description=description,
            scan_profile_id=scan_profile_id,
            auth_profile_id=auth_profile_id,
            interval_seconds=interval_seconds,
            last_scan_status="idle",
        )
        session.add(network)
        session.commit()
        network_id = network.id

    _ok(f"Réseau '{raw_subnet}' ajouté (id={network_id}).")
    print("  Le collecteur le prendra en charge lors de sa prochaine passe.")
    print("  Tip : vous pouvez ajouter d'autres profils sur ce même subnet avec 'network add'.")


# ---------------------------------------------------------------------------
# network remove
# ---------------------------------------------------------------------------

def cmd_network_remove(args: argparse.Namespace) -> None:
    factory = _get_session()
    with factory() as session:
        network = session.get(ScanNetwork, args.id)
        if network is None:
            _err(f"Réseau id={args.id} introuvable."); sys.exit(1)
        if network.last_scan_status == "running":
            _err("Un scan est en cours. Attendez sa fin avant de supprimer."); sys.exit(1)
        if _prompt(f"Supprimer '{network.subnet}' (id={network.id}) ? (oui/non)", "non").lower() not in ("oui","o","yes","y"):
            print("  Annulé."); return
        session.delete(network)
        session.commit()
    _ok(f"Réseau id={args.id} supprimé.")


# ---------------------------------------------------------------------------
# map create
# ---------------------------------------------------------------------------

_CATEGORY_TYPE_MAP: dict[str, str] = {
    "switch":   "switch",
    "router":   "router",
    "firewall": "firewall",
    "server":   "server",
    "ap":       "access_point",
    "storage":  "storage",
    "unknown":  "unknown",
}


def _device_status_str(snmp: str | None, icmp: str | None) -> str:
    if snmp == "Reachable" or icmp == "Reachable":
        return "online"
    if snmp == "Unreachable" or icmp == "Unreachable":
        return "offline"
    return "unknown"


def _pretty_xml(root: ET.Element) -> str:
    raw = ET.tostring(root, encoding="unicode")
    reparsed = minidom.parseString(raw)
    lines = reparsed.toprettyxml(indent="    ").splitlines()
    return "\n".join(line for line in lines if line.strip())


def cmd_map_create(args: argparse.Namespace) -> None:
    from orion_scanner.db.schema import Vendor
    factory  = _get_session()
    out_path = Path(args.output)
    filter_s = getattr(args, "filter_status", "all")

    with factory() as session:
        devices = session.scalars(select(Device)).all()
        if not devices:
            _err("Aucun equipement en base. Lancez d'abord un scan.")
            sys.exit(1)

        device_map: dict[str, dict] = {}
        for dev in devices:
            dev_type = "unknown"
            try:
                model    = session.get(DeviceModel, dev.model_id)
                family   = session.get(DeviceFamily, model.family_id) if model else None
                category = session.get(DeviceCategory, family.category_id) if family else None
                if category:
                    dev_type = _CATEGORY_TYPE_MAP.get(category.slug.lower(), "unknown")
            except Exception:
                pass

            mgmt_ip = "0.0.0.0"
            iface_candidates = []
            if dev.int_mgmt:
                ifc = session.get(Interface, dev.int_mgmt)
                if ifc:
                    iface_candidates = [ifc]
            if not iface_candidates:
                iface_candidates = list(dev.interfaces)
            for ifc in iface_candidates:
                map_row = session.scalar(
                    select(IpInterfaceMap)
                    .where(IpInterfaceMap.interface_id == ifc.id)
                    .where(IpInterfaceMap.is_primary == True)
                )
                if map_row:
                    ip_row = session.get(IpAddress, map_row.ip_address_id)
                    if ip_row:
                        mgmt_ip = str(ip_row.address).split("/")[0]
                        break

            ds = dev.device_status
            status = _device_status_str(
                ds.snmp_status if ds else None,
                ds.icmp_status if ds else None,
            )

            loc_name = ""
            if dev.location_id:
                loc = session.get(Location, dev.location_id)
                if loc:
                    loc_name = loc.name

            fw_version = ""
            if dev.firmware_id:
                fw = session.get(Firmware, dev.firmware_id)
                if fw:
                    fw_version = fw.version

            vendor_name = ""
            try:
                model  = session.get(DeviceModel, dev.model_id)
                family = session.get(DeviceFamily, model.family_id) if model else None
                if family:
                    v = session.get(Vendor, family.vendor_id)
                    if v:
                        vendor_name = v.name
            except Exception:
                pass

            device_map[str(dev.id)] = {
                "id":          str(dev.id),
                "hostname":    dev.hostname,
                "ip":          mgmt_ip,
                "type":        dev_type,
                "status":      status,
                "location":    loc_name,
                "vendor":      vendor_name,
                "serial":      dev.serial_number or "",
                "firmware":    fw_version,
                "contact":     dev.snmp_contact or "",
                "description": (dev.snmp_description or "")[:120],
            }

        if filter_s != "all":
            device_map = {k: v for k, v in device_map.items() if v["status"] == filter_s}
            if not device_map:
                _err(f"Aucun equipement avec statut '{filter_s}'.")
                sys.exit(1)

        links = session.scalars(select(NetworkLink)).all()
        if_to_device: dict[int, str] = {}
        if_to_name:   dict[int, str] = {}
        for dev in devices:
            if str(dev.id) not in device_map:
                continue
            for ifc in dev.interfaces:
                if_to_device[ifc.id] = str(dev.id)
                if_to_name[ifc.id]   = ifc.name or f"if{ifc.if_index}"

        root = ET.Element("network")
        root.set("generated_at", datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        root.set("device_count", str(len(device_map)))

        nodes_el = ET.SubElement(root, "nodes")
        for d in device_map.values():
            n = ET.SubElement(nodes_el, "node")
            n.set("id",     d["hostname"])
            n.set("uuid",   d["id"])
            n.set("type",   d["type"])
            n.set("ip",     d["ip"])
            n.set("status", d["status"])
            for attr in ("location", "vendor", "serial", "firmware", "contact"):
                if d[attr]:
                    n.set(attr, d[attr])
            if d["description"]:
                n.set("description", d["description"])

        links_el = ET.SubElement(root, "links")
        seen_pairs: set[tuple[str, str]] = set()
        link_count = 0

        for lnk in links:
            src_did = if_to_device.get(lnk.src_interface_id)
            dst_did = if_to_device.get(lnk.dst_interface_id)
            if not src_did or not dst_did or src_did == dst_did:
                continue
            if src_did not in device_map or dst_did not in device_map:
                continue
            pair = (min(src_did, dst_did), max(src_did, dst_did))
            seen_pairs.add(pair)
            link_count += 1
            src_info = device_map[src_did]
            dst_info = device_map[dst_did]
            le = ET.SubElement(links_el, "link")
            le.set("source",      src_info["hostname"])
            le.set("target",      dst_info["hostname"])
            le.set("source_uuid", src_did)
            le.set("target_uuid", dst_did)
            le.set("src_port",    if_to_name.get(lnk.src_interface_id, ""))
            le.set("dst_port",    if_to_name.get(lnk.dst_interface_id, ""))
            le.set("proto",       lnk.discovery_proto or "LLDP")
            le.set("link_type",   lnk.link_type or "Copper")
            if lnk.last_seen and hasattr(lnk.last_seen, "strftime"):
                le.set("last_seen", lnk.last_seen.strftime("%Y-%m-%dT%H:%M:%SZ"))

        root.set("link_count", str(link_count))

    xml_str = _pretty_xml(root)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(xml_str, encoding="utf-8")
    _ok(f"Cartographie generee : {out_path.resolve()}")
    print(f"  Equipements            : {len(device_map)}")
    print(f"  Liens (interfaces)     : {link_count}")
    print(f"  Paires device-a-device : {len(seen_pairs)}")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orion", description="Orion CLI")
    sub = parser.add_subparsers(dest="command", metavar="<commande>")
    sub.required = True

    p_profile = sub.add_parser("profile", help="Profils d'authentification")
    pp = p_profile.add_subparsers(dest="subcommand", metavar="<action>"); pp.required = True
    pp.add_parser("list",   help="Lister").set_defaults(func=cmd_profile_list)
    pp.add_parser("create", help="Créer").set_defaults(func=cmd_profile_create)
    p_del = pp.add_parser("delete", help="Supprimer")
    p_del.add_argument("id", type=int); p_del.set_defaults(func=cmd_profile_delete)

    p_sp = sub.add_parser("scan-profile", help="Profils de scan")
    ps = p_sp.add_subparsers(dest="subcommand", metavar="<action>"); ps.required = True
    ps.add_parser("list",   help="Lister").set_defaults(func=cmd_scan_profile_list)
    ps.add_parser("create", help="Créer").set_defaults(func=cmd_scan_profile_create)

    # ── map ─────────────────────────────────────────────────────────────────
    p_map = sub.add_parser("map", help="Cartographie réseau")
    pm = p_map.add_subparsers(dest="subcommand", metavar="<action>"); pm.required = True
    p_mc = pm.add_parser("create", help="Générer le XML de cartographie")
    p_mc.add_argument(
        "-o", "--output",
        default="orion_map.xml",
        help="Fichier de sortie (défaut: orion_map.xml)",
    )
    p_mc.add_argument(
        "--filter-status",
        choices=["online", "offline", "unknown", "all"],
        default="all",
        help="Filtrer les nœuds par statut (défaut: all)",
    )
    p_mc.set_defaults(func=cmd_map_create)

    p_net = sub.add_parser("network", help="Réseaux à scanner")
    pn = p_net.add_subparsers(dest="subcommand", metavar="<action>"); pn.required = True
    pn.add_parser("list",   help="Lister").set_defaults(func=cmd_network_list)
    pn.add_parser("active", help="Scans en cours").set_defaults(func=cmd_network_active)
    pn.add_parser("status", help="État détaillé").set_defaults(func=cmd_network_status)
    pn.add_parser("add",    help="Ajouter").set_defaults(func=cmd_network_add)
    p_rem = pn.add_parser("remove", help="Supprimer")
    p_rem.add_argument("id", type=int); p_rem.set_defaults(func=cmd_network_remove)

    return parser


def main() -> None:
    if not sys.stdin.isatty():
        print("ERROR: Orion CLI nécessite un terminal interactif.", file=sys.stderr)
        sys.exit(1)
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()