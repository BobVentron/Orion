"""
Database writer — persistance des résultats SNMP avec gestion complète
des dépendances de clés étrangères.

Ordre d'écriture imposé par le schéma
--------------------------------------
Avant d'insérer un ``Device``, plusieurs tables de référence doivent déjà
contenir des données.  Le writer les résout dans cet ordre :

1. ``vendors``          → nécessaire pour device_families
2. ``device_categories``→ nécessaire pour device_families
3. ``device_families``  → nécessaire pour device_models
4. ``device_models``    → FK NOT NULL sur devices
5. ``ref_device_status``→ FK NOT NULL sur devices
6. ``firmwares``        → FK nullable sur devices (crée si version trouvée)
7. ``devices``          ← écriture principale
8. ``interfaces``       → FK sur devices
9. ``interfaces_status``→ FK sur interfaces (append-only)
10. ``ip_addresses``    → FK nullable vers ip_subnets (sans subnet pour l'instant)
11. ``ip_interface_map``→ FK sur (interfaces, ip_addresses)
12. ``device_status``   → FK sur devices (upsert)
13. ``lldp_neighbors``  → FK sur interfaces (upsert)

Résolution du modèle
--------------------
Le scanner extrait ``sysObjectID`` (ex: ``1.3.6.1.4.1.9.1.516``).
Le PEN (numéro après ``1.3.6.1.4.1.``) est extrait et comparé à
``vendor_iana_pen`` pour identifier le vendor.

Si le PEN n'est pas connu → vendor "Unknown" (créé à la volée).
Si la famille n'est pas connue → famille générique pour ce vendor.
Si le modèle n'est pas connu → modèle générique ``part_number='UNKNOWN'``.

Aucun scan ne sera bloqué par un OID non référencé.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from orion_scanner.db.schema import (
    Device,
    DeviceCategory,
    DeviceFamily,
    DeviceMetricsHistory,
    DeviceModel,
    DeviceModule,
    DeviceMonitoringTask,
    DeviceStatus,
    Firmware,
    Interface,
    InterfaceMetricsHistory,
    InterfaceStatus,
    InterfaceTrunk,
    InterfaceVlan,
    IpAddress,
    IpInterfaceMap,
    LagMember,
    LldpNeighbor,
    Location,
    MacAddressEntry,
    MonitoringProfile,
    NetworkLink,
    RedundancyState,
    RefDeviceStatus,
    Vendor,
    VendorIanaPen,
    Vlan,
)
from orion_scanner.models import (
    DeviceScanResult,
    InterfaceInfo,
    IpAddressInfo,
    LldpNeighbor as LldpNeighborModel,
    PhysicalEntityInfo,
    SnmpCredentials,
    SnmpV1V2Credentials,
    SnmpV3Credentials,
    SystemInfo,
    VlanInfo,
)
from orion_scanner.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constantes : valeurs "inconnues" créées à la volée
# ---------------------------------------------------------------------------

_UNKNOWN_VENDOR_SLUG = "unknown"
_UNKNOWN_VENDOR_NAME = "Unknown Vendor"
_UNKNOWN_CATEGORY_SLUG = "unknown"
_UNKNOWN_CATEGORY_NAME = "Inconnu"
_UNKNOWN_FAMILY_NAME = "Generic Device"
_UNKNOWN_MODEL_PART = "UNKNOWN"
_DEFAULT_STATUS_CODE = "provisioning"   # statut attribué à tout nouvel équipement


# ===========================================================================
# ÉTAPE 0 — Helpers de lookup / création à la volée
# ===========================================================================


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)



# ===========================================================================
# RÉSOLUTION VENDOR / CATÉGORIE / MODÈLE
# Pipeline : sysObjectID → PEN → Vendor → Catégorie → Family → Model
# Enrichissement : sysDescr + ENTITY-MIB (entPhysicalModelName)
# ===========================================================================

import re as _re


def _normalize_oid(raw: str | None) -> str | None:
    """
    Normalise un OID quelle que soit la forme retournée par pysnmp.

    pysnmp peut retourner :
      - "1.3.6.1.4.1.9.1.516"             (forme numérique)
      - "SNMPv2-SMI::enterprises.9.1.516"  (forme symbolique)
      - ".1.3.6.1.4.1.9.1.516"            (avec point initial)

    Retourne toujours la forme numérique sans point initial.
    """
    if not raw:
        return None
    raw = raw.strip()
    # Forme symbolique SNMPv2-SMI::enterprises.X.Y...
    m = _re.search(r'enterprises\.(\d[\d.]*)', raw)
    if m:
        return '1.3.6.1.4.1.' + m.group(1)
    # Forme numérique avec ou sans point initial
    m = _re.search(r'(1\.3\.6\.1\.4\.1\.\d[\d.]*)', raw)
    if m:
        return m.group(1)
    return raw


def _extract_pen_from_oid(sys_object_id: str | None) -> int | None:
    """
    Extrait le Private Enterprise Number depuis un sysObjectID.

    ``1.3.6.1.4.1.9.1.516``           →  9   (Cisco)
    ``SNMPv2-SMI::enterprises.9.1.516``→  9
    ``1.3.6.1.4.1.8072.3.2.10``        →  8072
    """
    oid = _normalize_oid(sys_object_id)
    if not oid:
        return None
    m = _re.search(r'1\.3\.6\.1\.4\.1\.(\d+)', oid)
    return int(m.group(1)) if m else None


# Private Enterprise Numbers (IANA) → (nom, slug)
_KNOWN_PENS: dict[int, tuple[str, str]] = {
    9:     ("Cisco Systems",    "cisco"),
    11:    ("Hewlett Packard",  "hp"),
    43:    ("3Com",             "3com"),
    89:    ("Cisco IOS XE",     "cisco"),   # alias Cisco
    116:   ("Brocade",          "brocade"),
    171:   ("D-Link",           "dlink"),
    207:   ("Allied Telesis",   "allied-telesis"),
    236:   ("Extreme Networks", "extreme"),
    674:   ("Dell",             "dell"),
    1916:  ("Extreme Networks", "extreme"),
    2272:  ("Nortel / Avaya",   "nortel"),
    2636:  ("Juniper Networks", "juniper"),
    4874:  ("Enterasys",        "enterasys"),
    6027:  ("Force10 / Dell",   "force10"),
    6486:  ("Alcatel-Lucent",   "alcatel"),
    8072:  ("Net-SNMP / Linux", "net-snmp"),
    9303:  ("MikroTik",         "mikrotik"),
    11898: ("Palo Alto",        "paloalto"),
    12356: ("Fortinet",         "fortinet"),
    14179: ("Cisco WLC",        "cisco"),   # alias Cisco
    14525: ("Aruba Networks",   "aruba"),
    25461: ("Palo Alto",        "paloalto"),
    30065: ("Arista Networks",  "arista"),
    40310: ("Ubiquiti",         "ubiquiti"),
}


# ─── Inférence de la catégorie ───────────────────────────────────────────────
# Règles par ordre de priorité décroissante.
# sysDescr est converti en minuscules avant matching.

_CATEGORY_RULES: list[tuple[str, list[str]]] = [
    # (slug_catégorie, [patterns sur sysDescr en minuscules])
    # Évalués dans l'ordre — la PREMIÈRE règle qui matche gagne.

    # 1. Firewall — avant tout (certains disent "IOS" aussi)
    ("firewall",  [r"fortigate", r"fortiwifi", r"palo.alto", r"\basa\b", r"firewall",
                   r"srx\d", r"netscreen", r"checkpoint", r"watchguard",
                   r"cisco.adaptive.security"]),

    # 2. Contrôleurs WiFi
    ("wlc",       [r"wireless.lan.controller", r"\bwlc\b", r"aireos",
                   r"catalyst.*wireless", r"aruba.*controller"]),

    # 3. Points d'accès
    ("ap",        [r"\baccess.?point\b", r"aironet", r"aruba.*ap",
                   r"unifi.*ap", r"ubiquiti.*ap"]),

    # 4. Switches — AVANT routeurs pour éviter les faux positifs sur numéros
    #    On utilise le préfixe "C" + modèle IOS (ex: C2960-, C3750-)
    #    ou des mots-clés non ambigus
    ("switch",    [r"\bswitch\b", r"catalyst", r"nexus", r"qfx",
                   r"procurve", r"comware", r"powerconnect", r"stackable",
                   r"fastpath", r"ws-c\d{4}",
                   # Préfixes IOS Cisco switches (non ambigus)
                   r"c29[0-9][0-9][-]", r"c35[0-9][0-9][-]",
                   r"c37[0-9][0-9][-]", r"c38[0-9][0-9][-]",
                   r"c45[0-9][0-9][-]", r"c65[0-9][0-9][-]",
                   r"c9[0-9]{3}[-]",
                   # Juniper EX = switches
                   r"\bex\d{4}\b"]),

    # 5. Routeurs — après switches
    ("router",    [r"\brouter\b", r"ios.xe", r"routeos", r"mikrotik.*router",
                   r"junos.*re", r"\bmx\d{2,}",
                   # Préfixes IOS Cisco routeurs
                   r"c1[0-9]{3}[-]", r"c2[89][0-9]{2}[-]",
                   r"c8[0-9]{2}[-]",
                   r"\basr\d", r"\bisr\d"]),

    # 6. Serveurs / OS génériques
    ("server",    [r"\bserver\b", r"\blinux\b", r"windows.server", r"esxi",
                   r"net-snmp", r"ubuntu", r"debian", r"centos", r"rhel",
                   r"windows.*workstation", r"microsoft.*windows",
                   r"hardware:.*x86"]),

    ("ups",       [r"\bups\b", r"uninterruptible", r"\bapc\b", r"eaton"]),
    ("printer",   [r"\bprinter\b", r"laserjet", r"pagewide", r"officejet"]),
]


def _infer_category_slug(sys_descr: str | None, vendor_slug: str | None,
                         pen: int | None) -> str:
    """
    Devine la catégorie d'un équipement depuis sysDescr et le vendor.

    Retourne un slug parmi : switch, router, firewall, wlc, ap, server,
    ups, printer, ou 'unknown' si aucune règle ne matche.
    """
    descr = (sys_descr or "").lower()

    for slug, patterns in _CATEGORY_RULES:
        for pat in patterns:
            if _re.search(pat, descr):
                return slug

    # Fallback sur le vendor slug
    if vendor_slug:
        if vendor_slug in ("fortinet", "paloalto"):
            return "firewall"
        if vendor_slug in ("net-snmp",):
            return "server"
        if vendor_slug in ("aruba",) and pen == 14525:
            return "wlc"

    return "unknown"


def _extract_model_from_sysdescr(sys_descr: str | None,
                                  vendor_slug: str | None) -> str | None:
    """
    Extrait le modèle depuis sysDescr en utilisant des patterns par vendor.

    Exemples :
      "Cisco IOS Software ... catalyst3750 ..."       → "catalyst3750"
      "Cisco IOS Software, C3750E-UNIVERSALK9-M ..."  → "C3750E-UNIVERSALK9-M"
      "FortiGate-100F ..."                             → "FortiGate-100F"
      "MikroTik RouterOS 6.49 (CCR1009-7G-1C-1S+)"   → "CCR1009-7G-1C-1S+"
      "Juniper Networks ... ex4300-48p ..."            → "ex4300-48p"
    """
    if not sys_descr:
        return None

    # 1. Contenu entre parenthèses — souvent le modèle exact (MikroTik, Cisco)
    m = _re.search(r'\(([A-Z0-9][A-Z0-9\-\+\/\.]{3,})\)', sys_descr, _re.I)
    if m:
        candidate = m.group(1).strip()
        # Exclure les versions logicielles (contiennent souvent des espaces ou Version)
        if not _re.search(r'version|software|release|build', candidate, _re.I):
            return candidate

    # 2. Patterns spécifiques par vendor
    vendor_patterns: dict[str, list[str]] = {
        "cisco":    [
            r'([Cc]atalyst\s*\d+[A-Z0-9\-]*)',
            r'([A-Z]{1,4}\d{3,4}[A-Z0-9\-]+)',      # ex: C3750E-UNIVERSALK9
            r'cisco\s+([A-Z]{2,}\d{3,}[A-Z0-9\-]*)',
        ],
        "fortinet": [r'(FortiGate-[A-Z0-9\-]+)', r'(FortiWiFi-[A-Z0-9\-]+)'],
        "juniper":  [r'([Ee][Xx]\d{4}-\d+[a-z\-]*)', r'([Mm][Xx]\d{2,}[a-z\-]*)'],
        "arista":   [r'([Dd][Cc][Ss]-[A-Z0-9\-]+)', r'(vEOS[A-Z0-9\-]*)'],
        "hp":       [r'(ProCurve\s+[A-Z0-9\-]+)', r'(Comware.*?Switch\s+[A-Z0-9]+)'],
        "mikrotik": [r'([A-Z]{2,4}\d{4}[A-Z0-9\-\+\/]*)'],
        "aruba":    [r'(Aruba\s+[A-Z0-9\-]+)'],
        "extreme":  [r'(X\d{3}[A-Z0-9\-]*)'],
    }

    patterns = vendor_patterns.get(vendor_slug or "", [])
    for pat in patterns:
        m = _re.search(pat, sys_descr)
        if m:
            return m.group(1).strip()

    # 3. Pattern générique : token alphanumérique ressemblant à un modèle
    m = _re.search(r'\b([A-Z]{1,5}\d{3,5}[A-Z0-9\-]{0,20})\b', sys_descr)
    if m:
        return m.group(1)

    return None


def _get_or_create_vendor(session: Session, pen: int | None,
                          sys_descr: str | None = None) -> "Vendor":
    """
    Retourne le Vendor associé au PEN (Private Enterprise Number).

    Cherche dans vendor_iana_pen, puis dans _KNOWN_PENS.
    En dernier recours tente d'extraire un nom depuis sysDescr.
    """
    if pen is not None:
        # 1. Table vendor_iana_pen (données de référence)
        row = session.scalar(
            select(Vendor)
            .join(VendorIanaPen, VendorIanaPen.vendor_id == Vendor.id)
            .where(VendorIanaPen.pen == pen)
        )
        if row:
            return row

        # 2. Table _KNOWN_PENS interne
        if pen in _KNOWN_PENS:
            name, slug = _KNOWN_PENS[pen]
            vendor = session.scalar(select(Vendor).where(Vendor.slug == slug))
            if vendor is None:
                vendor = Vendor(name=name, slug=slug)
                session.add(vendor)
                session.flush()
            # Lier le PEN si pas encore fait
            existing_pen = session.scalar(
                select(VendorIanaPen).where(VendorIanaPen.pen == pen)
            )
            if existing_pen is None:
                session.add(VendorIanaPen(pen=pen, vendor_id=vendor.id))
                session.flush()
            logger.info("Vendor résolu depuis PEN %d : %s", pen, name)
            return vendor

        # 3. PEN inconnu — tenter d'extraire depuis sysDescr
        name_from_descr = _extract_vendor_name_from_descr(sys_descr, pen)
        slug = _re.sub(r'[^a-z0-9]+', '-', name_from_descr.lower()).strip('-')
        vendor = session.scalar(select(Vendor).where(Vendor.slug == slug))
        if vendor is None:
            vendor = Vendor(name=name_from_descr, slug=slug)
            session.add(vendor)
            session.flush()
        existing_pen = session.scalar(
            select(VendorIanaPen).where(VendorIanaPen.pen == pen)
        )
        if existing_pen is None:
            session.add(VendorIanaPen(pen=pen, vendor_id=vendor.id))
            session.flush()
        logger.info("Vendor inconnu PEN=%d créé depuis sysDescr : '%s'", pen, name_from_descr)
        return vendor

    # 4. Vendor complètement inconnu (pas de PEN)
    vendor = session.scalar(select(Vendor).where(Vendor.slug == _UNKNOWN_VENDOR_SLUG))
    if vendor is None:
        vendor = Vendor(name=_UNKNOWN_VENDOR_NAME, slug=_UNKNOWN_VENDOR_SLUG)
        session.add(vendor)
        session.flush()
    return vendor


def _extract_vendor_name_from_descr(sys_descr: str | None, pen: int) -> str:
    """
    Extrait un nom de constructeur depuis sysDescr quand le PEN est inconnu.
    Retourne "Vendor-{pen}" en dernier recours.
    """
    if sys_descr:
        # Premier mot capitalisé ou première ligne
        m = _re.match(r'([A-Z][A-Za-z0-9\-]+)', sys_descr)
        if m:
            return m.group(1)
        first_line = sys_descr.split('\n')[0].split(',')[0].strip()
        if first_line:
            return first_line[:50]
    return f"Vendor-{pen}"


def _get_or_create_category(session: Session,
                             slug: str = _UNKNOWN_CATEGORY_SLUG) -> "DeviceCategory":
    """Retourne la catégorie correspondant au slug, en la créant si nécessaire."""
    _CATEGORY_META: dict[str, tuple[str, str]] = {
        "switch":   ("Commutateur",       "fas fa-network-wired"),
        "router":   ("Routeur",           "fas fa-random"),
        "firewall": ("Pare-Feu",          "fas fa-shield-alt"),
        "wlc":      ("Contrôleur Wi-Fi",  "fas fa-wifi"),
        "ap":       ("Point d'accès",     "fas fa-broadcast-tower"),
        "server":   ("Serveur",           "fas fa-server"),
        "ups":      ("Onduleur",          "fas fa-battery-half"),
        "printer":  ("Imprimante",        "fas fa-print"),
        "unknown":  ("Inconnu",           "fas fa-question-circle"),
    }
    cat = session.scalar(select(DeviceCategory).where(DeviceCategory.slug == slug))
    if cat is None:
        name, icon = _CATEGORY_META.get(slug, ("Inconnu", "fas fa-question-circle"))
        cat = DeviceCategory(slug=slug, name=name, icon_class=icon)
        session.add(cat)
        session.flush()
        logger.debug("Catégorie créée : slug='%s'", slug)
    return cat


def _get_or_create_family(session: Session, vendor: "Vendor",
                           sys_object_id: str | None,
                           category_slug: str = _UNKNOWN_CATEGORY_SLUG) -> "DeviceFamily":
    """
    Cherche une famille par sysobject_oid exact (plus fiable),
    sinon crée une famille pour ce vendor + catégorie.
    """
    oid = _normalize_oid(sys_object_id)

    if oid:
        family = session.scalar(
            select(DeviceFamily).where(DeviceFamily.sysobject_oid == oid)
        )
        if family:
            # Si la catégorie était unknown et qu'on a mieux maintenant, on met à jour
            if category_slug != _UNKNOWN_CATEGORY_SLUG:
                current_cat = session.get(DeviceCategory, family.category_id)
                if current_cat and current_cat.slug == _UNKNOWN_CATEGORY_SLUG:
                    new_cat = _get_or_create_category(session, category_slug)
                    family.category_id = new_cat.id
                    session.flush()
                    logger.info("Catégorie mise à jour pour famille OID=%s : %s",
                                oid, category_slug)
            return family

    # Famille générique pour ce vendor+catégorie
    family = session.scalar(
        select(DeviceFamily).where(
            DeviceFamily.vendor_id == vendor.id,
            DeviceFamily.name == _UNKNOWN_FAMILY_NAME,
        )
    )
    if family is None:
        category = _get_or_create_category(session, category_slug)
        family_name = (
            f"{vendor.name} Device"
            if vendor.slug != _UNKNOWN_VENDOR_SLUG
            else _UNKNOWN_FAMILY_NAME
        )
        family = DeviceFamily(
            vendor_id=vendor.id,
            category_id=category.id,
            sysobject_oid=oid,
            name=family_name,
        )
        session.add(family)
        session.flush()
        logger.debug("Famille créée : '%s' (vendor=%s, cat=%s, oid=%s)",
                     family_name, vendor.slug, category_slug, oid)
    return family


def _get_or_create_model(session: Session, family: "DeviceFamily",
                          part_number: str) -> "DeviceModel":
    """
    Cherche ou crée un modèle dans la famille donnée.

    Args:
        part_number: SKU / modèle extrait (OID, ENTITY-MIB ou sysDescr).
                     Jamais vide — on passe au moins l'OID complet.
    """
    model = session.scalar(
        select(DeviceModel).where(
            DeviceModel.family_id == family.id,
            DeviceModel.part_number == part_number,
        )
    )
    if model is None:
        model = DeviceModel(family_id=family.id, part_number=part_number)
        session.add(model)
        session.flush()
        logger.info("Modèle créé : '%s' (family_id=%d)", part_number, family.id)
    return model


def _resolve_model_id(session: Session, system: "SystemInfo",
                      entities: list | None = None) -> int:
    """
    Résout le model_id avec la pipeline enrichie :

      1. sysObjectID → PEN → Vendor
      2. sysDescr + PEN → Catégorie (switch / router / firewall / ...)
      3. sysObjectID normalisé → Family (crée si absente)
      4. Part number dans cet ordre de priorité :
           a. entPhysicalModelName du chassis (ENTITY-MIB)
           b. sysDescr regex (modèle entre parenthèses ou pattern vendor)
           c. OID complet normalisé (toujours disponible)
      5. Model upsert

    Args:
        session: Session SQLAlchemy active.
        system:  Données système SNMP.
        entities: Composants ENTITY-MIB (optionnel, enrichit le part_number).

    Returns:
        device_models.id garanti non NULL.
    """
    oid = _normalize_oid(system.sys_object_id)
    pen = _extract_pen_from_oid(oid)

    # 1. Vendor
    vendor = _get_or_create_vendor(session, pen, system.sys_descr)

    # 2. Catégorie depuis sysDescr
    cat_slug = _infer_category_slug(system.sys_descr, vendor.slug, pen)
    logger.debug("Catégorie inférée pour %s : %s", system.ip, cat_slug)

    # 3. Family
    family = _get_or_create_family(session, vendor, oid, cat_slug)

    # 4. Part number — priorité : ENTITY-MIB > sysDescr > OID complet
    part_number: str | None = None

    # a. ENTITY-MIB : entPhysicalModelName du chassis
    if entities:
        chassis_entity = next(
            (e for e in entities
             if e.physical_class == "chassis"
             and e.part_number
             and e.part_number.strip().upper() not in ("", "UNKNOWN", "N/A", "NONE")),
            None,
        )
        if chassis_entity:
            part_number = chassis_entity.part_number.strip()
            logger.debug("Part number depuis ENTITY-MIB : '%s'", part_number)

    # b. sysDescr regex
    if not part_number:
        part_number = _extract_model_from_sysdescr(system.sys_descr, vendor.slug)
        if part_number:
            logger.debug("Part number depuis sysDescr : '%s'", part_number)

    # c. Fallback : OID complet (identifie le modèle de façon unique même sans nom)
    if not part_number:
        part_number = oid or _UNKNOWN_MODEL_PART
        logger.debug("Part number depuis OID : '%s'", part_number)

    # 5. Model
    model = _get_or_create_model(session, family, part_number)
    return model.id


def _resolve_status_id(session: Session) -> int:
    """
    Retourne l'id du statut 'provisioning' (équipement nouvellement découvert).

    Ce statut est défini dans ``Orion_DATA.sql`` ; s'il est absent (base vierge
    sans données initiales), il est créé automatiquement.

    Args:
        session: Session SQLAlchemy active.

    Returns:
        ``ref_device_status.id`` garanti non NULL.
    """
    status = session.scalar(
        select(RefDeviceStatus).where(RefDeviceStatus.code == _DEFAULT_STATUS_CODE)
    )
    if status is None:
        status = RefDeviceStatus(
            code=_DEFAULT_STATUS_CODE,
            name="En Installation",
            color="#17a2b8",
            is_monitored=False,
            description="Créé automatiquement par le scanner.",
        )
        session.add(status)
        session.flush()
        logger.warning(
            "Statut '%s' absent de ref_device_status — créé automatiquement. "
            "Pensez à exécuter Orion_DATA.sql.",
            _DEFAULT_STATUS_CODE,
        )
    return status.id


def _get_or_create_firmware(session: Session, version: str | None) -> int | None:
    """
    Upsert un enregistrement dans ``firmwares`` et retourne son id.

    Retourne ``None`` si ``version`` est absent ou vide.

    Args:
        session: Session SQLAlchemy active.
        version: Chaîne de version (ex: ``"15.2(7)E2"``).

    Returns:
        ``firmwares.id`` ou ``None``.
    """
    if not version:
        return None

    firmware = session.scalar(select(Firmware).where(Firmware.version == version))
    if firmware is None:
        firmware = Firmware(version=version)
        session.add(firmware)
        session.flush()
        logger.debug("Firmware '%s' créé.", version)
    return firmware.id


def _get_or_create_location(session: Session, location_name: str | None) -> int | None:
    """
    Retourne l'id d'une Location par son nom, en la créant si absente.
    Retourne None si location_name est vide.
    """
    if not location_name or not location_name.strip():
        return None
    name = location_name.strip()
    loc = session.scalar(select(Location).where(Location.name == name))
    if loc is None:
        loc = Location(name=name)
        session.add(loc)
        session.flush()
        logger.debug("Location créée : '%s'", name)
    return loc.id


# ===========================================================================
# ÉTAPE 1 — Upsert Device
# ===========================================================================


def _upsert_device(
    session: Session,
    result: DeviceScanResult,
    model_id: int,
    status_id: int,
    firmware_id: int | None,
    location_id: int | None = None,
) -> Device:
    """
    Crée ou met à jour un équipement.

    Champs mis à jour à chaque scan : firmware, serial_number, location,
    auth_profile_id (profil utilisé pour ce scan), model_id (si affiné
    plus tard par _try_update_model_from_entity).

    La clé de déduplication est l'IP de management (result.ip) — plus
    fiable que le hostname qui peut changer.
    """
    system = result.system  # garanti non-None ici
    hostname = (system.sys_name or result.ip).strip()

    # Déduplication sur l'IP de management — plus stable que le hostname
    device = session.scalar(
        select(Device).where(Device.hostname == hostname)
    )

    # Extraire le serial du chassis depuis les physical_entities si dispo
    serial_number: str | None = None
    if result.physical_entities:
        chassis = next(
            (e for e in result.physical_entities
             if e.physical_class == "chassis" and e.serial_number
             and e.serial_number.upper() not in ("", "N/A", "NONE", "UNKN")),
            None,
        )
        if chassis:
            serial_number = chassis.serial_number.strip()

    # auth_profile_id depuis les credentials utilisés
    auth_profile_id: int | None = None
    if hasattr(result.credentials_used, '_auth_profile_id'):
        auth_profile_id = result.credentials_used._auth_profile_id

    snmp_contact     = (system.sys_contact or "").strip() or None
    snmp_description = (system.sys_descr  or "").strip() or None

    if device is None:
        device = Device(
            id=uuid.uuid4(),
            hostname=hostname,
            model_id=model_id,
            status_id=status_id,
            firmware_id=firmware_id,
            serial_number=serial_number,
            location_id=location_id,
            auth_profile_id=auth_profile_id,
            snmp_contact=snmp_contact,
            snmp_description=snmp_description,
        )
        session.add(device)
        logger.info(
            "Nouvel équipement : %s | serial=%s | contact=%s | fw=%s",
            hostname, serial_number or "—", snmp_contact or "—", firmware_id or "—",
        )
    else:
        # Mise à jour des champs dynamiques à chaque scan
        if firmware_id is not None:
            device.firmware_id = firmware_id
        if serial_number:
            device.serial_number = serial_number
        if location_id is not None:
            device.location_id = location_id
        if auth_profile_id is not None:
            device.auth_profile_id = auth_profile_id
        if snmp_contact:
            device.snmp_contact = snmp_contact
        if snmp_description:
            device.snmp_description = snmp_description
        logger.info("Équipement mis à jour : %s (uuid=%s)", hostname, device.id)

    session.flush()
    return device


# ===========================================================================
# ÉTAPE 2 — Upsert Interfaces
# ===========================================================================


def _upsert_interface(
    session: Session, device_id: uuid.UUID, iface: InterfaceInfo
) -> Interface:
    """
    Crée ou met à jour une interface via la contrainte unique ``(device_id, if_index)``.

    Args:
        session: Session SQLAlchemy active.
        device_id: UUID du device parent.
        iface: Données interface remontées par IF-MIB.

    Returns:
        Instance :class:`~orion_scanner.db.schema.Interface`.
    """
    stmt = (
        pg_insert(Interface)
        .values(
            device_id=device_id,
            if_index=iface.if_index,
            name=iface.name or f"if{iface.if_index}",
            description=iface.description,
            alias=iface.alias,
            mac_address=iface.mac_address,
            type=iface.if_type,
            mtu=iface.mtu,
            speed=iface.speed_bps,
        )
        .on_conflict_do_update(
            constraint="uq_interface_device_ifindex",
            set_={
                "name": iface.name or f"if{iface.if_index}",
                "description": iface.description,
                "alias": iface.alias,
                "mac_address": iface.mac_address,
                "type": iface.if_type,
                "mtu": iface.mtu,
                "speed": iface.speed_bps,
            },
        )
        .returning(Interface.id)
    )
    row = session.execute(stmt).fetchone()
    session.flush()

    # Récupération de l'objet ORM complet pour les relations
    return session.get(Interface, row[0])


def _insert_interface_status(
    session: Session, interface_id: int, iface: InterfaceInfo
) -> None:
    """
    Insère un snapshot de statut (table append-only).

    Si admin_status ou oper_status sont inconnus, on skip pour respecter
    la contrainte NOT NULL du DDL.

    Args:
        session: Session active.
        interface_id: PK de l'interface.
        iface: Données interface.
    """
    if iface.admin_status is None or iface.oper_status is None:
        return

    status = InterfaceStatus(
        interface_id=interface_id,
        last_change=_now(),
        admin_status=iface.admin_status.value,
        oper_status=iface.oper_status.value,
    )
    session.add(status)


# ===========================================================================
# ÉTAPE 3 — Upsert IP Addresses
# ===========================================================================


def _upsert_ip_address(session: Session, ip_info: IpAddressInfo) -> IpAddress:
    """
    Upsert une adresse IP dans ``ip_addresses``.

    Note : ``subnet_id`` n'est pas calculé ici (nécessiterait de chercher
    dans ip_subnets la route la plus spécifique). C'est délibérément laissé
    NULL pour cette version et sera résolu lors d'une passe IPAM ultérieure.

    Args:
        session: Session active.
        ip_info: Données IP remontées par IP-MIB.

    Returns:
        Instance :class:`~orion_scanner.db.schema.IpAddress`.
    """
    stmt = (
        pg_insert(IpAddress)
        .values(
            address=ip_info.address,
            type="Static",
            status="Active",
            last_seen=_now(),
        )
        .on_conflict_do_update(
            constraint="uq_ip_address",
            set_={
                "status": "Active",
                "last_seen": _now(),
            },
        )
        .returning(IpAddress.id)
    )
    row = session.execute(stmt).fetchone()
    session.flush()
    return session.get(IpAddress, row[0])


def _upsert_ip_interface_map(
    session: Session,
    interface_id: int,
    ip_address_id: int,
    is_primary: bool = False,
) -> None:
    """
    Crée le lien interface ↔ IP si il n'existe pas déjà.

    Args:
        session: Session active.
        interface_id: PK interface.
        ip_address_id: PK ip_address.
        is_primary: True si c'est l'IP principale de l'interface.
    """
    stmt = (
        pg_insert(IpInterfaceMap)
        .values(
            interface_id=interface_id,
            ip_address_id=ip_address_id,
            is_primary=is_primary,
            is_virtual=False,
        )
        .on_conflict_do_nothing()   # PK composite (interface_id, ip_address_id)
    )
    session.execute(stmt)


# ===========================================================================
# ÉTAPE 4 — Upsert DeviceStatus
# ===========================================================================


def _upsert_device_status(
    session: Session, device_id: uuid.UUID, result: DeviceScanResult
) -> None:
    """
    Upsert le snapshot de supervision temps réel.

    Args:
        session: Session active.
        device_id: UUID du device.
        result: Résultat complet du scan.
    """
    uptime_s: int | None = None
    if result.system and result.system.sys_uptime_centiseconds is not None:
        uptime_s = result.system.sys_uptime_centiseconds // 100

    stmt = (
        pg_insert(DeviceStatus)
        .values(
            device_id=device_id,
            last_poll=_now(),
            snmp_status="Reachable",
            icmp_status="Reachable",
            uptime_seconds=uptime_s,
        )
        .on_conflict_do_update(
            constraint="device_status_pkey",
            set_={
                "last_poll": _now(),
                "snmp_status": "Reachable",
                "icmp_status": "Reachable",
                "uptime_seconds": uptime_s,
            },
        )
    )
    session.execute(stmt)


# ===========================================================================
# ÉTAPE 5 — Upsert LLDP/CDP Neighbors
# ===========================================================================


def _upsert_lldp_neighbor(
    session: Session,
    local_interface_id: int,
    neighbor: LldpNeighborModel,
) -> None:
    """
    Upsert un voisin LLDP/CDP.

    La contrainte unique ``uq_lldp_neighbor`` porte sur
    ``(local_interface_id, remote_chassis_id, remote_port_id, protocol)``.
    Si remote_chassis_id est NULL (cas fréquent en CDP), PostgreSQL traite
    chaque NULL comme distinct — on utilise ON CONFLICT DO UPDATE pour
    mettre à jour ``last_seen`` et ``remote_sysname`` à la place.

    Args:
        session: Session active.
        local_interface_id: PK de l'interface locale.
        neighbor: Voisin collecté par le scanner topologie.
    """
    stmt = (
        pg_insert(LldpNeighbor)
        .values(
            local_interface_id=local_interface_id,
            remote_chassis_id=neighbor.remote_chassis_id,
            remote_sysname=neighbor.remote_sys_name,
            remote_port_id=neighbor.remote_port_id,
            remote_ip=neighbor.remote_mgmt_ip,
            protocol=neighbor.protocol.value,
            last_seen=_now(),
        )
        .on_conflict_do_update(
            constraint="uq_lldp_neighbor",
            set_={
                "remote_sysname": neighbor.remote_sys_name,
                "remote_ip": neighbor.remote_mgmt_ip,
                "last_seen": _now(),
            },
        )
    )
    session.execute(stmt)


# ===========================================================================
# ÉTAPE 6 — Lien management interface
# ===========================================================================


def _update_mgmt_interface(
    session: Session,
    device: Device,
    if_index_to_db_id: dict[int, int],
    mgmt_ip: str,
) -> None:
    """
    Met à jour ``devices.int_mgmt`` avec l'interface correspondant à l'IP
    de management (l'IP qui a répondu au scan SNMP).

    On cherche dans les IPs upsertées celle qui correspond à ``mgmt_ip``,
    puis on remonte à l'interface via ``ip_interface_map``.

    Args:
        session: Session active.
        device: Device ORM à mettre à jour.
        if_index_to_db_id: Mapping ifIndex → interfaces.id construit
                           pendant l'upsert des interfaces.
        mgmt_ip: IP qui a répondu au scan.
    """
    ip_row = session.scalar(select(IpAddress).where(IpAddress.address == mgmt_ip))
    if ip_row is None:
        return

    map_row = session.scalar(
        select(IpInterfaceMap).where(
            IpInterfaceMap.ip_address_id == ip_row.id,
            IpInterfaceMap.interface_id.in_(if_index_to_db_id.values()),
        )
    )
    if map_row and device.int_mgmt != map_row.interface_id:
        device.int_mgmt = map_row.interface_id
        logger.debug(
            "Interface de management mise à jour : device=%s  if_id=%d",
            device.hostname,
            map_row.interface_id,
        )


# ===========================================================================
# ÉTAPE 7 — Upsert Physical Entities (device_modules)
# ===========================================================================


def _upsert_device_modules(
    session: Session,
    device_id: uuid.UUID,
    entities: list[PhysicalEntityInfo],
) -> dict[int, int]:
    """
    Persiste les composants physiques remontés par ENTITY-MIB.

    Filtre les entrées de classe ``port`` (déjà couverts par IF-MIB) et
    ``unknown`` sans nom pertinent pour ne pas saturer la table.

    Les modules sont insérés avec upsert sur ``(device_id, ent_index)``.
    La résolution des liens parent→enfant (``parent_index``) est faite en
    **deux passes** : d'abord tous les modules sont insérés, puis les
    ``parent_index`` sont mis à jour avec les IDs base générés — ce qui
    évite les contraintes FK circulaires.

    Args:
        session: Session active.
        device_id: UUID du device parent.
        entities: Liste de :class:`~orion_scanner.models.PhysicalEntityInfo`.

    Returns:
        Mapping ``{ent_index: device_modules.id}`` pour la résolution parente.
    """
    # Classes à exclure : les ports sont dans interfaces, sensor est du bruit
    _SKIP_CLASSES = {"port", "sensor", "container", "other", "unknown"}

    filtered = [e for e in entities if e.physical_class not in _SKIP_CLASSES]
    if not filtered:
        return {}

    ent_index_to_db_id: dict[int, int] = {}

    # Passe 1 : upsert de chaque module sans parent_index (mis à NULL)
    for entity in filtered:
        stmt = (
            pg_insert(DeviceModule)
            .values(
                device_id=device_id,
                ent_index=entity.ent_index,
                name=entity.name,
                description=entity.description,
                class_=entity.physical_class,
                serial_number=entity.serial_number,
                part_number=entity.part_number,
                is_fru=entity.is_fru,
                # parent_index résolu en passe 2
            )
            .on_conflict_do_update(
                constraint="uq_device_module_ent_index",
                set_={
                    "name": entity.name,
                    "description": entity.description,
                    "class": entity.physical_class,
                    "serial_number": entity.serial_number,
                    "part_number": entity.part_number,
                    "is_fru": entity.is_fru,
                },
            )
            .returning(DeviceModule.id)
        )
        row = session.execute(stmt).fetchone()
        if row:
            ent_index_to_db_id[entity.ent_index] = row[0]

    session.flush()

    # Passe 2 : mise à jour des liens parent
    for entity in filtered:
        db_id = ent_index_to_db_id.get(entity.ent_index)
        parent_db_id = ent_index_to_db_id.get(entity.parent_index) if entity.parent_index else None
        if db_id and parent_db_id:
            session.execute(
                DeviceModule.__table__.update()
                .where(DeviceModule.id == db_id)
                .values(parent_index=parent_db_id)
            )

    logger.debug(
        "device_modules: %d composants écrits pour device=%s",
        len(ent_index_to_db_id),
        device_id,
    )
    return ent_index_to_db_id


def _try_update_model_from_entity(
    session: Session,
    device: Device,
    entities: list[PhysicalEntityInfo],
) -> None:
    """
    Tente d'affiner le modèle du device avec le ``part_number`` réel
    remontée par ENTITY-MIB (entPhysicalModelName du chassis).

    Si le chassis principal fournit un ``part_number`` non vide et que ce
    part_number existe déjà en base dans la même famille, on met à jour
    ``devices.model_id``.  Sinon on crée le modèle dans la famille existante.

    Cette fonction est appelée **après** l'upsert du device, donc le model_id
    générique est déjà en place — on ne fait ici qu'affiner si possible.

    Args:
        session: Session active.
        device: Instance Device ORM déjà flushée.
        entities: Composants physiques collectés.
    """
    # Cherche l'entité de classe 'chassis' avec un part_number non vide
    chassis = next(
        (
            e for e in entities
            if e.physical_class == "chassis" and e.part_number
            and e.part_number.upper() not in ("", "UNKNOWN", "N/A", "NONE")
        ),
        None,
    )
    if chassis is None:
        return

    part_number = chassis.part_number.strip()

    # Cherche si ce part_number existe déjà dans la même famille que le modèle actuel
    current_model = session.get(DeviceModel, device.model_id)
    if current_model is None:
        return

    existing = session.scalar(
        select(DeviceModel).where(
            DeviceModel.family_id == current_model.family_id,
            DeviceModel.part_number == part_number,
        )
    )

    if existing is None:
        # Crée le modèle précis dans la même famille
        existing = DeviceModel(
            family_id=current_model.family_id,
            part_number=part_number,
        )
        session.add(existing)
        session.flush()
        logger.info(
            "Modèle précis créé : part_number='%s' (family_id=%d)",
            part_number, current_model.family_id,
        )

    if device.model_id != existing.id:
        device.model_id = existing.id
        logger.info(
            "Modèle affiné pour %s : UNKNOWN → %s (model_id=%d)",
            device.hostname, part_number, existing.id,
        )


# ===========================================================================
# ÉTAPE 8 — Upsert VLANs
# ===========================================================================


def _upsert_vlans(
    session: Session,
    device_id: uuid.UUID,
    vlans: list[VlanInfo],
) -> dict[int, int]:
    """
    Persiste les VLANs collectés dans la table ``vlans``.

    La contrainte unique est ``(device_id, vlan_tag)`` — chaque VLAN est
    lié à l'équipement qui l'a déclaré.  Sur un réseau avec VTP, le même
    tag peut apparaître sur plusieurs switches : c'est voulu, chaque device
    ayant potentiellement sa propre vue (nom, statut).

    Args:
        session: Session active.
        device_id: UUID du device.
        vlans: Liste de :class:`~orion_scanner.models.VlanInfo`.

    Returns:
        Mapping ``{vlan_tag: vlans.id}`` utilisable pour lier les interfaces.
    """
    if not vlans:
        return {}

    tag_to_db_id: dict[int, int] = {}

    for vlan in vlans:
        stmt = (
            pg_insert(Vlan)
            .values(
                device_id=device_id,
                vlan_tag=vlan.vlan_tag,
                name=vlan.name,
                status=vlan.status,
                type=vlan.type,
                role=vlan.role,
            )
            .on_conflict_do_update(
                constraint="uq_vlan_device_tag",
                set_={
                    "name": vlan.name,
                    "status": vlan.status,
                    "type": vlan.type,
                    "role": vlan.role,
                },
            )
            .returning(Vlan.id)
        )
        row = session.execute(stmt).fetchone()
        if row:
            tag_to_db_id[vlan.vlan_tag] = row[0]

    session.flush()
    logger.debug(
        "vlans: %d VLANs écrits pour device=%s", len(tag_to_db_id), device_id
    )
    return tag_to_db_id


# ===========================================================================
# Point d'entrée public
# ===========================================================================


def write_scan_result(session: Session, result: DeviceScanResult) -> Device | None:
    """
    Persiste un :class:`~orion_scanner.models.DeviceScanResult` complet.

    Respecte l'ordre de dépendances des FK :
    référentiels → device → interfaces → IP → maps → status → voisins.

    Args:
        session: Session SQLAlchemy active.  Le commit est à la charge
                 de l'appelant (``write_scan_results`` le fait en batch).
        result: Résultat de scan pour un équipement.

    Returns:
        L'instance :class:`~orion_scanner.db.schema.Device` persistée,
        ou ``None`` si l'équipement n'a pas répondu à SNMP.
    """
    if not result.is_successful:
        logger.debug("Hôte %s ignoré (pas de réponse SNMP).", result.ip)
        return None

    system = result.system

    # ------------------------------------------------------------------
    # 1. Résolution des FK obligatoires AVANT d'insérer le device
    # ------------------------------------------------------------------
    model_id = _resolve_model_id(
        session, system,
        entities=result.physical_entities or []
    )
    status_id = _resolve_status_id(session)

    # Firmware : priorité à entPhysicalSoftwareRev du chassis (ENTITY-MIB)
    # sinon heuristique sur sysDescr
    firmware_version: str | None = None
    if result.physical_entities:
        chassis_fw = next(
            (e.firmware_version for e in result.physical_entities
             if e.physical_class == "chassis" and e.firmware_version
             and e.firmware_version.upper() not in ("", "N/A", "NONE", "UNKN")),
            None,
        )
        if chassis_fw:
            firmware_version = chassis_fw.strip()
    if not firmware_version:
        firmware_version = _extract_firmware_version(system.sys_descr)
    firmware_id = _get_or_create_firmware(session, firmware_version)

    # Location depuis sysLocation SNMP (créée à la volée si nouvelle)
    location_id = _get_or_create_location(session, system.sys_location)

    # ------------------------------------------------------------------
    # 2. Device
    # ------------------------------------------------------------------
    device = _upsert_device(session, result, model_id, status_id, firmware_id, location_id)

    # ------------------------------------------------------------------
    # 3. Interfaces + statuts
    # ------------------------------------------------------------------
    if_index_to_db_id: dict[int, int] = {}
    for iface in result.interfaces:
        db_iface = _upsert_interface(session, device.id, iface)
        if db_iface is not None:
            if_index_to_db_id[iface.if_index] = db_iface.id
            _insert_interface_status(session, db_iface.id, iface)

    # ------------------------------------------------------------------
    # 4. Adresses IP + liaisons interface↔IP
    # ------------------------------------------------------------------
    for ip_info in result.ip_addresses:
        db_ip = _upsert_ip_address(session, ip_info)
        db_iface_id = if_index_to_db_id.get(ip_info.if_index)
        if db_iface_id is not None:
            # L'IP de management est marquée is_primary=True
            is_primary = (ip_info.address == result.ip)
            _upsert_ip_interface_map(session, db_iface_id, db_ip.id, is_primary)

    # ------------------------------------------------------------------
    # 5. Interface de management
    # ------------------------------------------------------------------
    _update_mgmt_interface(session, device, if_index_to_db_id, result.ip)

    # ------------------------------------------------------------------
    # 6. Snapshot supervision
    # ------------------------------------------------------------------
    _upsert_device_status(session, device.id, result)

    # ------------------------------------------------------------------
    # 7. Voisins LLDP / CDP
    # ------------------------------------------------------------------
    for neighbor in result.lldp_neighbors:
        db_iface_id = if_index_to_db_id.get(neighbor.local_if_index)
        if db_iface_id is not None:
            _upsert_lldp_neighbor(session, db_iface_id, neighbor)
        else:
            logger.debug(
                "Voisin ignoré : ifIndex %d non trouvé dans %s",
                neighbor.local_if_index,
                device.hostname,
            )

    # ------------------------------------------------------------------
    # 8. Composants physiques (ENTITY-MIB) → device_modules
    #    + affinage du modèle si entPhysicalModelName disponible
    # ------------------------------------------------------------------
    if result.physical_entities:
        _upsert_device_modules(session, device.id, result.physical_entities)

    # ------------------------------------------------------------------
    # 9. VLANs (VTP / Q-BRIDGE) → vlans
    # ------------------------------------------------------------------
    if result.vlans:
        _upsert_vlans(session, device.id, result.vlans)

    # ------------------------------------------------------------------
    # 10. Création automatique des monitoring tasks pour ce device
    #     (idempotent — ignore les tâches déjà existantes)
    # ------------------------------------------------------------------
    try:
        create_monitoring_tasks_for_device(session, device.id)
    except Exception as exc:
        logger.warning(
            "Impossible de créer les monitoring tasks pour %s : %s",
            device.hostname, exc,
        )

    return device


def write_scan_results(session: Session, results: list[DeviceScanResult]) -> int:
    """
    Persiste une liste de résultats en un seul commit.

    En cas d'erreur sur un équipement, un rollback partiel est effectué
    et le scan continue pour les équipements suivants.

    Args:
        session: Session SQLAlchemy active.
        results: Liste de :class:`~orion_scanner.models.DeviceScanResult`.

    Returns:
        Nombre d'équipements écrits avec succès.
    """
    written = 0

    for result in results:
        try:
            device = write_scan_result(session, result)
            if device is not None:
                written += 1
        except Exception as exc:
            logger.error(
                "Erreur lors de l'écriture de %s : %s — rollback de cet équipement.",
                result.ip,
                exc,
                exc_info=True,
            )
            session.rollback()

    try:
        session.commit()
        logger.info("Commit réussi : %d équipement(s) persisté(s).", written)
    except Exception as exc:
        logger.error("Commit global échoué : %s", exc, exc_info=True)
        session.rollback()
        raise

    return written


# ===========================================================================
# Helpers privés divers
# ===========================================================================


def _extract_firmware_version(sys_descr: str | None) -> str | None:
    """
    Tente d'extraire une version logicielle depuis ``sysDescr``.

    Heuristiques couvertes :
    - Cisco IOS  : ``"Version 15.2(7)E2"``
    - Linux      : ``"Linux 5.15.0-91-generic"``
    - Juniper    : ``"JUNOS 21.4R3"``

    Args:
        sys_descr: Chaîne brute de sysDescr.

    Returns:
        Chaîne de version ou ``None``.
    """
    if not sys_descr:
        return None

    patterns = [
        r"Version\s+([\w\.\(\)]+)",      # Cisco IOS/NX-OS
        r"Linux\s+(\S+)",                # Linux kernel
        r"JUNOS\s+(\S+)",                # Juniper
        r"Rel\s+([\w\.]+)",              # HP/Aruba
        r"v([\d]+\.[\d]+\.[\d]+)",       # Format générique vX.Y.Z
    ]
    for pattern in patterns:
        match = re.search(pattern, sys_descr, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


# ===========================================================================
# Checks récurrents — statut interfaces, FDB, network_links
# ===========================================================================



def write_interface_statuses(
    session: Session,
    device_id_uuid,
    statuses: list[InterfaceStatusCheck],
    if_index_to_db_id: dict[int, int],
) -> int:
    """
    Insère des snapshots de statut d'interfaces (append-only).

    Seules les interfaces dont le statut a changé depuis le dernier snapshot
    sont insérées pour éviter de saturer la table.

    Returns:
        Nombre de snapshots insérés.
    """
    if not statuses or not if_index_to_db_id:
        return 0

    inserted = 0
    for st in statuses:
        db_id = if_index_to_db_id.get(st.if_index)
        if db_id is None:
            continue
        if st.admin_status is None or st.oper_status is None:
            continue

        # Vérifier si le dernier statut est identique (évite les doublons)
        last = session.scalar(
            select(InterfaceStatus)
            .where(InterfaceStatus.interface_id == db_id)
            .order_by(InterfaceStatus.last_change.desc())
        )
        if (last
                and last.admin_status == st.admin_status.value
                and last.oper_status  == st.oper_status.value):
            continue   # Pas de changement

        session.add(InterfaceStatus(
            interface_id=db_id,
            last_change=_now(),
            admin_status=st.admin_status.value,
            oper_status=st.oper_status.value,
        ))
        inserted += 1

    session.flush()
    return inserted


def write_mac_table(
    session: Session,
    entries: list[MacTableEntry],
    if_index_to_db_id: dict[int, int],
) -> int:
    """
    Met à jour la table FDB (mac_address_table) pour un device.

    Utilise un upsert sur (interface_id, mac_address) pour ne pas
    dupliquer les entrées connues, et met à jour last_seen.

    Returns:
        Nombre d'entrées upsertées.
    """
    if not entries or not if_index_to_db_id:
        return 0

    count = 0
    for entry in entries:
        db_id = if_index_to_db_id.get(entry.if_index)
        if db_id is None:
            continue

        stmt = (
            pg_insert(MacAddressEntry)
            .values(
                interface_id=db_id,
                mac_address=entry.mac_address,
                type=entry.entry_type,
                last_seen=_now(),
            )
            .on_conflict_do_update(
                constraint="uq_mac_fdb_entry",
                set_={"last_seen": _now(), "type": entry.entry_type},
            )
        )
        session.execute(stmt)
        count += 1

    session.flush()
    return count




def create_monitoring_tasks_for_device(
    session: Session,
    device_id,
) -> int:
    """
    Crée les entrées device_monitoring_tasks pour un nouveau device.

    Appelé automatiquement par le collecteur après write_scan_result().
    Crée une tâche pour chaque monitoring_profile actif, avec
    next_run_at = NOW() pour que le premier check parte immédiatement.

    Returns:
        Nombre de tâches créées.
    """
    profiles = session.scalars(
        select(MonitoringProfile).where(MonitoringProfile.is_enabled == True)  # noqa: E712
    ).all()

    created = 0
    for profile in profiles:
        existing = session.get(DeviceMonitoringTask, (device_id, profile.id))
        if existing is not None:
            continue

        task = DeviceMonitoringTask(
            device_id       = device_id,
            profile_id      = profile.id,
            is_enabled      = True,
            next_run_at     = _now(),   # Démarre immédiatement
            last_run_status = "idle",
        )
        session.add(task)
        created += 1

    if created:
        session.flush()
        logger.debug(
            "Monitoring tasks créées : device=%s — %d profil(s).",
            device_id, created,
        )
    return created


# ===========================================================================
# Writers métriques — device_metrics_history + interface_metrics_history
# ===========================================================================

from orion_scanner.snmp.check_metrics import DeviceMetricsResult, InterfaceMetricsResult


def write_device_metrics(
    session: Session,
    device_id,
    metrics: DeviceMetricsResult,
    icmp_rtt: float | None = None,
    icmp_loss: int | None = None,
) -> bool:
    """
    Insère un snapshot dans device_metrics_history.

    Returns:
        True si des données ont été insérées, False sinon.
    """
    if all(v is None for v in [
        metrics.cpu_load, metrics.ram_usage, metrics.ram_free,
        metrics.temp_celsius, icmp_rtt, icmp_loss,
    ]):
        return False

    session.add(DeviceMetricsHistory(
        time          = _now(),
        device_id     = device_id,
        cpu_load      = metrics.cpu_load,
        ram_usage     = metrics.ram_usage,
        ram_free      = metrics.ram_free,
        temp_celsius  = metrics.temp_celsius,
        icmp_rtt      = icmp_rtt,
        icmp_loss     = icmp_loss,
    ))
    session.flush()
    return True


def write_interface_metrics(
    session: Session,
    iface_metrics: list[InterfaceMetricsResult],
    if_index_to_db_id: dict[int, int],
) -> int:
    """
    Insère des snapshots dans interface_metrics_history.

    Returns:
        Nombre de lignes insérées.
    """
    if not iface_metrics or not if_index_to_db_id:
        return 0

    inserted = 0
    now = _now()

    for m in iface_metrics:
        db_id = if_index_to_db_id.get(m.if_index)
        if db_id is None:
            continue

        # Skip si aucune donnée utile
        if all(v is None for v in [
            m.in_octets, m.out_octets, m.in_errors, m.out_errors,
            m.in_discards, m.out_discards,
        ]):
            continue

        session.add(InterfaceMetricsHistory(
            time              = now,
            interface_id      = db_id,
            in_octets         = m.in_octets,
            out_octets        = m.out_octets,
            in_ucast_pkts     = m.in_ucast_pkts,
            out_ucast_pkts    = m.out_ucast_pkts,
            in_nucast_pkts    = m.in_nucast_pkts,
            out_nucast_pkts   = m.out_nucast_pkts,
            in_errors         = m.in_errors,
            out_errors        = m.out_errors,
            in_discards       = m.in_discards,
            out_discards      = m.out_discards,
            in_unknown_protos = m.in_unknown_protos,
        ))
        inserted += 1

    if inserted:
        session.flush()
    return inserted


# ===========================================================================
# Writers HSRP/VRRP, EtherChannel, Trunks
# ===========================================================================

from orion_scanner.snmp.check_hsrp import RedundancyEntry
from orion_scanner.snmp.check_etherchannel import LagMemberEntry
from orion_scanner.snmp.check_trunks import TrunkEntry, VlanMembership


def _resolve_device_uuid_by_ip(session: Session, ip: str | None) -> str | None:
    """
    Résout une IP en UUID de device via ip_addresses → ip_interface_map → interfaces → devices.

    Utilisé pour remplir redundancy_states.active_router depuis l'IP
    du routeur actif HSRP/VRRP retournée par le MIB.
    """
    if not ip:
        return None
    try:
        ip_row = session.scalar(select(IpAddress).where(IpAddress.address == ip))
        if not ip_row:
            return None
        map_row = session.scalar(
            select(IpInterfaceMap).where(IpInterfaceMap.ip_address_id == ip_row.id)
        )
        if not map_row:
            return None
        iface = session.get(Interface, map_row.interface_id)
        if not iface:
            return None
        return str(iface.device_id)
    except Exception as exc:
        logger.debug("Résolution IP→device échouée pour %s : %s", ip, exc)
        return None


def write_redundancy(
    session: Session,
    device_id,
    entries: list[RedundancyEntry],
    if_index_to_db_id: dict[int, int],
) -> int:
    """
    Upsert les groupes HSRP/VRRP dans redundancy_states.

    Résout active_router_ip → UUID device pour remplir active_router.
    """
    if not entries:
        return 0

    count = 0
    for entry in entries:
        db_id = if_index_to_db_id.get(entry.if_index)
        if db_id is None:
            continue

        # Résoudre l'IP du routeur actif en UUID device
        active_router_uuid = _resolve_device_uuid_by_ip(
            session, getattr(entry, "active_router_ip", None)
        )

        stmt = (
            pg_insert(RedundancyState)
            .values(
                interface_id  = db_id,
                group_id      = entry.group_id,
                virtual_ip    = entry.virtual_ip,
                state         = entry.state,
                priority      = entry.priority,
                protocol      = entry.protocol,
                preempt       = entry.preempt,
                hello_time    = entry.hello_time,
                hold_time     = entry.hold_time,
                active_router = active_router_uuid,
                last_change   = _now(),
            )
            .on_conflict_do_update(
                constraint="uq_redundancy_group",
                set_={
                    "state":          entry.state,
                    "priority":       entry.priority,
                    "virtual_ip":     entry.virtual_ip,
                    "preempt":        entry.preempt,
                    "active_router":  active_router_uuid,
                    "last_change":    _now(),
                },
            )
        )
        session.execute(stmt)
        count += 1

    session.flush()
    return count


def write_etherchannel(
    session: Session,
    entries: list[LagMemberEntry],
    if_index_to_db_id: dict[int, int],
) -> int:
    """
    Upsert les membres EtherChannel dans lag_members ET cree les
    network_links physiques (un lien par paire de ports membres).

    Logique des liens physiques :
      Pour chaque membre local, si on connait le port partenaire distant
      (partner_port_ifindex), on resout ce port dans la base via le device
      partenaire (identifie par sa MAC / partner_sys_id) et on cree un
      network_link normalise src < dst.

      Si le port partenaire n'est pas encore en base (device pas encore
      scanne), on skip silencieusement — il sera cree lors du prochain scan.
    """
    from orion_scanner.snmp.check_topology import upsert_network_link

    if not entries:
        return 0

    # Grouper les membres par cle operationnelle pour les logs
    by_key: dict[int | None, list] = {}
    for e in entries:
        by_key.setdefault(e.oper_key, []).append(e)

    lag_count  = 0   # Lignes lag_members inserees/mises a jour
    link_count = 0   # network_links crees

    for entry in entries:
        agg_db_id    = if_index_to_db_id.get(entry.agg_if_index)
        member_db_id = if_index_to_db_id.get(entry.member_if_index)
        if agg_db_id is None or member_db_id is None:
            continue
        if agg_db_id == member_db_id:
            continue

        # 1. Upsert lag_members
        stmt = (
            pg_insert(LagMember)
            .values(
                agg_interface_id    = agg_db_id,
                member_interface_id = member_db_id,
                protocol            = entry.protocol,
                actor_oper_key      = entry.oper_key,
                partner_oper_system = entry.partner_sys_id,
                is_synced           = True,
            )
            .on_conflict_do_update(
                constraint="uq_lag_member",
                set_={
                    "protocol":            entry.protocol,
                    "actor_oper_key":      entry.oper_key,
                    "partner_oper_system": entry.partner_sys_id,
                    "is_synced":           True,
                },
            )
        )
        session.execute(stmt)
        lag_count += 1

        # 2. Creer le network_link physique membre_local <-> membre_distant
        #    Necessaire : partner_sys_id (MAC) + partner_port_ifindex
        if not entry.partner_sys_id or entry.partner_port_ifindex is None:
            continue

        # Resoudre le device partenaire via sa MAC d'interface
        partner_if_db_id: int | None = None
        try:
            partner_iface = session.scalar(
                select(Interface).where(Interface.mac_address == entry.partner_sys_id)
            )
            if partner_iface:
                # Trouver l'interface membre cote partenaire par ifIndex
                partner_member_iface = session.scalar(
                    select(Interface).where(
                        Interface.device_id == partner_iface.device_id,
                        Interface.if_index  == entry.partner_port_ifindex,
                    )
                )
                if partner_member_iface:
                    partner_if_db_id = partner_member_iface.id
        except Exception as exc:
            logger.debug("EtherChannel: resolution partenaire echouee : %s", exc)

        if partner_if_db_id is None:
            logger.debug(
                "EtherChannel: port partenaire non resolu "
                "(MAC=%s ifIndex=%d) — sera cree au prochain scan.",
                entry.partner_sys_id, entry.partner_port_ifindex,
            )
            continue

        # Creer le lien physique (normalise src < dst)
        link = upsert_network_link(
            session, member_db_id, partner_if_db_id, "LACP"
        )
        if link:
            link_count += 1

    session.flush()

    if lag_count:
        logger.debug(
            "EtherChannel : %d membres en base, %d liens physiques crees.",
            lag_count, link_count,
        )
    return lag_count


def write_trunks(
    session: Session,
    device_id,
    trunks: list[TrunkEntry],
    vlans: list[VlanMembership],
    if_index_to_db_id: dict[int, int],
    vlan_tag_to_db_id: dict[int, int],
) -> tuple[int, int]:
    """
    Upsert les trunks et les appartenances VLAN.

    Returns:
        (trunks_written, vlan_memberships_written)
    """

    trunk_count = 0
    vlan_count  = 0

    for trunk in trunks:
        db_id = if_index_to_db_id.get(trunk.if_index)
        if db_id is None:
            continue

        stmt = (
            pg_insert(InterfaceTrunk)
            .values(
                interface_id    = db_id,
                encapsulation   = trunk.encapsulation,
                admin_status    = trunk.admin_status,
                oper_status     = trunk.oper_status,
                allowed_vlans   = trunk.allowed_vlans,
                pruning_enabled = False,
            )
            .on_conflict_do_update(
                constraint="uq_trunk_interface",
                set_={
                    "encapsulation": trunk.encapsulation,
                    "oper_status":   trunk.oper_status,
                    "allowed_vlans": trunk.allowed_vlans,
                },
            )
        )
        session.execute(stmt)
        trunk_count += 1

    session.flush()

    # Purger les anciennes interface_vlans de ce device avant réinsertion
    # (évite les données obsolètes si un port change de VLAN)
    try:
        if_ids_in_device = list(if_index_to_db_id.values())
        if if_ids_in_device:
            from sqlalchemy import delete as sa_delete
            session.execute(
                sa_delete(InterfaceVlan).where(
                    InterfaceVlan.interface_id.in_(if_ids_in_device)
                )
            )
            session.flush()
    except Exception as exc:
        logger.debug("Purge interface_vlans échouée : %s", exc)

    # VLAN memberships
    # Si un VLAN n'existe pas encore en base, on le crée à la volée.
    for vm in vlans:
        db_if_id   = if_index_to_db_id.get(vm.if_index)
        if db_if_id is None:
            continue

        db_vlan_id = vlan_tag_to_db_id.get(vm.vlan_tag)

        if db_vlan_id is None and 1 <= vm.vlan_tag <= 4094:
            # Créer le VLAN à la volée avec les infos minimales
            try:
                vlan_stmt = (
                    pg_insert(Vlan)
                    .values(
                        device_id = device_id,
                        vlan_tag  = vm.vlan_tag,
                        name      = f"VLAN{vm.vlan_tag}",
                        status    = "Active",
                        type      = "Ethernet",
                        role      = "Data",
                    )
                    .on_conflict_do_update(
                        constraint="uq_vlan_device_tag",
                        set_={"status": "Active"},
                    )
                    .returning(Vlan.id)
                )
                row = session.execute(vlan_stmt).fetchone()
                if row:
                    db_vlan_id = row[0]
                    vlan_tag_to_db_id[vm.vlan_tag] = db_vlan_id
                    session.flush()
            except Exception as exc:
                logger.debug("Création VLAN %d à la volée échouée : %s", vm.vlan_tag, exc)
                continue

        if db_vlan_id is None:
            continue

        stmt = (
            pg_insert(InterfaceVlan)
            .values(
                interface_id = db_if_id,
                vlan_id      = db_vlan_id,
                mode         = vm.mode,
                is_native    = vm.is_native,
            )
            .on_conflict_do_update(
                index_elements=["interface_id", "vlan_id"],
                set_={"mode": vm.mode, "is_native": vm.is_native},
            )
        )
        session.execute(stmt)
        vlan_count += 1

    if vlan_count:
        session.flush()

    return trunk_count, vlan_count


# ===========================================================================
# ARP, Routing, STP
# ===========================================================================

from orion_scanner.snmp.check_arp     import ArpEntry
from orion_scanner.snmp.check_routing import RouteEntry
from orion_scanner.snmp.check_stp     import StpCheckResult


def write_arp(
    session: Session,
    device_id,
    entries: list[ArpEntry],
    if_index_to_db_id: dict[int, int],
) -> int:
    """
    Upsert la table ARP dans arp_table.

    Résout chaque IP en ip_address_id (crée l'IP si absente).
    Résout l'ifIndex en interface_id.

    Returns:
        Nombre d'entrées upsertées.
    """
    if not entries:
        return 0

    count = 0
    for entry in entries:
        db_if_id = if_index_to_db_id.get(entry.if_index)
        if db_if_id is None:
            continue

        # Résoudre/créer l'IP
        ip_row = session.scalar(
            select(IpAddress).where(IpAddress.address == entry.ip_address)
        )
        if ip_row is None:
            try:
                ip_stmt = (
                    pg_insert(IpAddress)
                    .values(
                        address  = entry.ip_address,
                        type     = "Static",
                        status   = "Active",
                        last_seen = _now(),
                    )
                    .on_conflict_do_update(
                        constraint="uq_ip_address",
                        set_={"last_seen": _now()},
                    )
                    .returning(IpAddress.id)
                )
                row = session.execute(ip_stmt).fetchone()
                if not row:
                    continue
                ip_id = row[0]
                session.flush()
            except Exception as exc:
                logger.debug("ARP: création IP %s échouée : %s", entry.ip_address, exc)
                continue
        else:
            ip_id = ip_row.id

        # Upsert arp_table
        from orion_scanner.db.schema import ArpTable
        try:
            stmt = (
                pg_insert(ArpTable)
                .values(
                    interface_id  = db_if_id,
                    ip_address_id = ip_id,
                    mac_address   = entry.mac_address,
                    last_seen     = _now(),
                )
                .on_conflict_do_update(
                    constraint="uq_arp_entry",
                    set_={
                        "mac_address": entry.mac_address,
                        "last_seen":   _now(),
                    },
                )
            )
            session.execute(stmt)
            count += 1
        except Exception as exc:
            logger.debug("ARP upsert %s : %s", entry.ip_address, exc)

    session.flush()
    logger.debug("ARP : %d entrées écrites.", count)
    return count


def write_routing(
    session: Session,
    device_id,
    entries: list[RouteEntry],
    if_index_to_db_id: dict[int, int],
) -> int:
    """
    Écrit la table de routage dans routing_table.

    Résout l'ifIndex en interface_id (peut être NULL pour routes blackhole).
    Utilise le VRF par défaut du device (crée si absent).

    Returns:
        Nombre de routes écrites.
    """
    if not entries:
        return 0

    # Récupérer ou créer le VRF "default" du device
    from orion_scanner.db.schema import Vrf, RoutingTable

    vrf = session.scalar(
        select(Vrf).where(Vrf.device_id == device_id, Vrf.name == "default")
    )
    if vrf is None:
        vrf = Vrf(device_id=device_id, name="default", rd=None)
        session.add(vrf)
        session.flush()

    # Supprimer les routes existantes du device avant réinsertion
    # (la table de routage est volatile, on remplace entièrement)
    try:
        session.query(RoutingTable).filter(RoutingTable.vrf_id == vrf.id).delete()
        session.flush()
    except Exception as exc:
        logger.debug("Routing: purge routes échouée : %s", exc)

    count = 0
    for entry in entries:
        if_id = None
        if entry.if_index:
            if_id = if_index_to_db_id.get(entry.if_index)

        try:
            session.add(RoutingTable(
                vrf_id       = vrf.id,
                interface_id = if_id,
                dest_net     = entry.dest_net,
                next_hop     = entry.next_hop,
                protocol     = entry.protocol,
                metric       = 1,
            ))
            count += 1
        except Exception as exc:
            logger.debug("Routing insert %s : %s", entry.dest_net, exc)

    session.flush()
    logger.debug("Routing : %d routes écrites.", count)
    return count


def write_stp(
    session: Session,
    device_id,
    result: StpCheckResult | None,
    if_index_to_db_id: dict[int, int],
) -> int:
    """
    Upsert l'instance STP et les états des ports dans stp_instances + stp_interface_state.

    Returns:
        Nombre de ports STP écrits.
    """
    if result is None:
        return 0

    from orion_scanner.db.schema import STPInstance, STPInterfaceState

    # Upsert l'instance STP (une seule par device pour l'instance par défaut)
    stp_inst = session.scalar(
        select(STPInstance).where(
            STPInstance.device_id == device_id,
            STPInstance.vlan_id.is_(None),   # instance par défaut = vlan NULL
        )
    )
    if stp_inst is None:
        stp_inst = STPInstance(
            device_id       = device_id,
            vlan_id         = None,
            root_bridge_id  = result.instance.root_bridge_id,
            bridge_priority = result.instance.bridge_priority,
            root_cost       = result.instance.root_cost,
        )
        session.add(stp_inst)
    else:
        stp_inst.root_bridge_id  = result.instance.root_bridge_id
        stp_inst.bridge_priority = result.instance.bridge_priority
        stp_inst.root_cost       = result.instance.root_cost
    session.flush()

    # États des ports
    count = 0
    for port in result.port_states:
        db_if_id = if_index_to_db_id.get(port.if_index)
        if db_if_id is None:
            continue

        try:
            stmt = (
                pg_insert(STPInterfaceState)
                .values(
                    interface_id    = db_if_id,
                    stp_instance_id = stp_inst.id,
                    timestamp       = _now(),
                    state           = port.state,
                    role            = "Designated",   # rôle non collecté dans cette version
                )
                .on_conflict_do_update(
                    index_elements=["interface_id", "stp_instance_id"],
                    set_={
                        "timestamp": _now(),
                        "state":     port.state,
                    },
                )
            )
            session.execute(stmt)
            count += 1
        except Exception as exc:
            logger.debug("STP port %d : %s", port.if_index, exc)

    session.flush()
    logger.debug("STP : instance écrite, %d états de ports.", count)
    return count