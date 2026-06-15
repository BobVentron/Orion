"""
ENTITY-MIB collector (RFC 6933 / RFC 2737).

Collecte la table ``entPhysicalTable`` qui décrit la hiérarchie physique
complète d'un équipement : chassis, cartes, ports, alimentations, ventilateurs…

OIDs collectés (entPhysicalTable = 1.3.6.1.2.1.47.1.1.1.1)
------------------------------------------------------------
Col  1  entPhysicalDescr          Description courte
Col  2  entPhysicalVendorType      OID du type constructeur
Col  4  entPhysicalContainedIn     Index du parent (0 = racine)
Col  5  entPhysicalClass           Classe (énumération IANAPhysicalClass)
Col  7  entPhysicalName            Nom court (ex: "GigabitEthernet1/0/1")
Col 10  entPhysicalSoftwareRev     Version firmware du composant
Col 11  entPhysicalSerialNum       Numéro de série
Col 13  entPhysicalModelName       Référence constructeur (SKU)
Col 14  entPhysicalIsFRU           Field Replaceable Unit (TruthValue)

Mapping entPhysicalClass (IANAPhysicalClass)
--------------------------------------------
1=other, 2=unknown, 3=chassis, 4=backplane, 5=container, 6=powerSupply,
7=fan, 8=sensor, 9=module, 10=port, 11=stack, 12=cpu
"""

from __future__ import annotations

from orion_scanner.models import PhysicalEntityInfo
from orion_scanner.snmp.client import SnmpClient, SnmpError
from orion_scanner.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# OID base + colonnes
# ---------------------------------------------------------------------------

_ENT_PHYSICAL_TABLE = "1.3.6.1.2.1.47.1.1.1.1"

_COL_DESCR = 1
_COL_CONTAINED_IN = 4
_COL_CLASS = 5
_COL_NAME = 7
_COL_SOFTWARE_REV = 10
_COL_SERIAL_NUM = 11
_COL_MODEL_NAME = 13
_COL_IS_FRU = 14

# IANAPhysicalClass integer → slug lisible
_CLASS_MAP: dict[str, str] = {
    "1": "other",
    "2": "unknown",
    "3": "chassis",
    "4": "backplane",
    "5": "container",
    "6": "powerSupply",
    "7": "fan",
    "8": "sensor",
    "9": "module",
    "10": "port",
    "11": "stack",
    "12": "cpu",
}

# Classes considérées comme du matériel utile (on exclut "other" et "unknown"
# pour ne pas saturer la base avec des entrées vides)
_USEFUL_CLASSES = {
    "chassis", "backplane", "powerSupply", "fan", "module", "stack", "cpu"
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _walk_col(client: SnmpClient, col: int) -> dict[str, str]:
    """Walk une colonne de entPhysicalTable et retourne {index: value}."""
    oid = f"{_ENT_PHYSICAL_TABLE}.{col}"
    try:
        rows = client.walk(oid)
    except SnmpError as exc:
        logger.debug("entPhysical col %d walk failed on %s: %s", col, client.ip, exc)
        return {}

    result: dict[str, str] = {}
    for full_oid, value in rows:
        if value.lower().startswith("no such"):
            continue
        # L'index est le dernier composant de l'OID
        idx = full_oid.rsplit(".", 1)[-1]
        result[idx] = value.strip()
    return result


def _is_fru(raw: str | None) -> bool:
    """Convertit TruthValue SNMP (1=true, 2=false) en bool Python."""
    return raw == "1"


# ---------------------------------------------------------------------------
# Collecteur principal
# ---------------------------------------------------------------------------


def collect_physical_entities(client: SnmpClient) -> list[PhysicalEntityInfo]:
    """
    Collecte la table ENTITY-MIB entPhysicalTable.

    Filtre les classes peu utiles (``other``, ``unknown``, ``port``,
    ``container``, ``sensor``) pour ne conserver que les composants matériels
    significatifs : chassis, modules, alimentations, ventilateurs, CPUs…

    Les ``port`` sont déjà couverts par IF-MIB ; les dupliquer dans
    ``device_modules`` créerait du bruit sans valeur ajoutée.

    Args:
        client: Client SNMP configuré.

    Returns:
        Liste de :class:`~orion_scanner.models.PhysicalEntityInfo`.
        Retourne une liste vide si l'équipement n'implémente pas ENTITY-MIB.
    """
    # Walk de toutes les colonnes nécessaires
    descrs = _walk_col(client, _COL_DESCR)

    if not descrs:
        # L'équipement n'implémente pas ENTITY-MIB
        logger.debug("ENTITY-MIB non disponible sur %s.", client.ip)
        return []

    contained_ins = _walk_col(client, _COL_CONTAINED_IN)
    classes = _walk_col(client, _COL_CLASS)
    names = _walk_col(client, _COL_NAME)
    sw_revs = _walk_col(client, _COL_SOFTWARE_REV)
    serials = _walk_col(client, _COL_SERIAL_NUM)
    models = _walk_col(client, _COL_MODEL_NAME)
    is_frus = _walk_col(client, _COL_IS_FRU)

    entities: list[PhysicalEntityInfo] = []

    for idx in sorted(descrs, key=lambda x: int(x) if x.isdigit() else 0):
        raw_class = classes.get(idx, "2")  # défaut = unknown
        physical_class = _CLASS_MAP.get(raw_class, raw_class)

        # On ne filtre PAS ici pour ne rien perdre — le writer decide
        # ce qu'il persiste. On exclut seulement les "port" (IF-MIB le gère)
        # et les entrées sans nom ni description.
        name = names.get(idx) or descrs.get(idx, "")
        if not name:
            continue

        raw_parent = contained_ins.get(idx, "0")
        try:
            parent_index = int(raw_parent)
        except ValueError:
            parent_index = 0

        try:
            ent_index = int(idx)
        except ValueError:
            continue

        entity = PhysicalEntityInfo(
            ent_index=ent_index,
            name=name,
            description=descrs.get(idx),
            physical_class=physical_class,
            serial_number=serials.get(idx) or None,
            part_number=models.get(idx) or None,
            firmware_version=sw_revs.get(idx) or None,
            parent_index=parent_index,
            is_fru=_is_fru(is_frus.get(idx)),
        )
        entities.append(entity)

    logger.debug(
        "ENTITY-MIB: %d composants collectés sur %s.", len(entities), client.ip
    )
    return entities
