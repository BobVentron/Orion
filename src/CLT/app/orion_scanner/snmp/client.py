"""
Client SNMP — compatible pysnmp-lextudio 6.x (et fallback 5.x / 4.x).

Historique des changements d'API pysnmp
-----------------------------------------
pysnmp ≤ 5.x  :  getCmd / bulkCmd sont des **générateurs async**
                  → ``async for errInd, errStat, errIdx, vbs in getCmd(...)``

pysnmp 6.x    :  getCmd / nextCmd sont des **coroutines ordinaires**
                  → ``errInd, errStat, errIdx, vbs = await getCmd(...)``
                  → nextCmd retourne un var_bind_table (liste de listes, 2D)
                  → le WALK se fait en appelant nextCmd() en boucle manuelle

Points critiques v6.x
----------------------
1. Le SnmpEngine NE DOIT PAS être réutilisé entre plusieurs asyncio.run().
   Chaque asyncio.run() crée une nouvelle event loop et détruit la précédente.
   Un engine créé dans la loop A reste attaché à la loop A (détruite) —
   tous les appels suivants se bloquent silencieusement.
   → Solution : créer un SnmpEngine() NEUF dans chaque coroutine.

2. nextCmd v6.x retourne un var_bind_table (tableau 2D) :
   [ [ObjectType(oid, val)], [ObjectType(oid2, val2)], ... ]
   et non une liste plate comme en v5.
   → Solution : itérer sur les lignes, extraire row[0] pour chaque ligne.

3. lexicographicMode=False doit être passé à nextCmd pour qu'il s'arrête
   automatiquement en fin d'arborescence (sinon boucle infinie possible).
"""

from __future__ import annotations

import asyncio
import inspect as _inspect
import warnings
from typing import Any

# Silence le RuntimeWarning de dépréciation pysnmp-lextudio
warnings.filterwarnings("ignore", category=RuntimeWarning, module="pysnmp")

# ---------------------------------------------------------------------------
# Détection du sous-module hlapi disponible
# ---------------------------------------------------------------------------
_hlapi: Any = None
_import_path = ""

for _candidate in [
    "pysnmp.hlapi.v3arch.asyncio",   # lextudio 6 / pysnmp 6
    "pysnmp.hlapi.asyncio",          # lextudio 5 / pysnmp 5
    "pysnmp.hlapi",                  # pysnmp ≤ 4
]:
    try:
        import importlib as _il
        _hlapi = _il.import_module(_candidate)
        _import_path = _candidate
        break
    except ImportError:
        continue

if _hlapi is None:
    raise ImportError(
        "Impossible d'importer pysnmp. Installez-le avec : pip install pysnmp"
    )

# ---------------------------------------------------------------------------
# Extraction des symboles depuis le module détecté
# ---------------------------------------------------------------------------
CommunityData      = _hlapi.CommunityData
ContextData        = _hlapi.ContextData
ObjectIdentity     = _hlapi.ObjectIdentity
ObjectType         = _hlapi.ObjectType
SnmpEngine         = _hlapi.SnmpEngine
UdpTransportTarget = _hlapi.UdpTransportTarget
UsmUserData        = _hlapi.UsmUserData
getCmd             = _hlapi.getCmd
nextCmd            = _hlapi.nextCmd
bulkCmd            = getattr(_hlapi, "bulkCmd", None)  # absent de certaines versions

# Protocoles auth — présents partout
usmNoAuthProtocol      = _hlapi.usmNoAuthProtocol
usmNoPrivProtocol      = _hlapi.usmNoPrivProtocol
usmHMACMD5AuthProtocol = _hlapi.usmHMACMD5AuthProtocol
usmHMACSHAAuthProtocol = _hlapi.usmHMACSHAAuthProtocol
usmDESPrivProtocol     = _hlapi.usmDESPrivProtocol
usmAesCfb128Protocol   = _hlapi.usmAesCfb128Protocol

# Protocoles étendus — dégradation gracieuse si absents
usmHMAC128SHA224AuthProtocol = getattr(_hlapi, "usmHMAC128SHA224AuthProtocol", usmHMACSHAAuthProtocol)
usmHMAC192SHA256AuthProtocol = getattr(_hlapi, "usmHMAC192SHA256AuthProtocol", usmHMACSHAAuthProtocol)
usmHMAC256SHA384AuthProtocol = getattr(_hlapi, "usmHMAC256SHA384AuthProtocol", usmHMACSHAAuthProtocol)
usmHMAC384SHA512AuthProtocol = getattr(_hlapi, "usmHMAC384SHA512AuthProtocol", usmHMACSHAAuthProtocol)
usmAesCfb192Protocol         = getattr(_hlapi, "usmAesCfb192Protocol",         usmAesCfb128Protocol)
usmAesCfb256Protocol         = getattr(_hlapi, "usmAesCfb256Protocol",         usmAesCfb128Protocol)

# ---------------------------------------------------------------------------
# Détection de la version d'API (v6 = coroutine, v5 = générateur async)
# ---------------------------------------------------------------------------
_APIV6: bool = _inspect.iscoroutinefunction(getCmd)

# ---------------------------------------------------------------------------
# Imports internes
# ---------------------------------------------------------------------------
from orion_scanner.models import (
    SnmpCredentials,
    SnmpV1V2Credentials,
    SnmpV3Credentials,
    SnmpVersion,
    V3AuthProto,
    V3PrivProto,
)
from orion_scanner.utils.logger import get_logger

logger = get_logger(__name__)
logger.debug("pysnmp chargé depuis %s  (API v6=%s)", _import_path, _APIV6)

# ---------------------------------------------------------------------------
# Mapping credentials → protocoles pysnmp
# ---------------------------------------------------------------------------

_AUTH_PROTO_MAP = {
    V3AuthProto.MD5:    usmHMACMD5AuthProtocol,
    V3AuthProto.SHA:    usmHMACSHAAuthProtocol,
    V3AuthProto.SHA224: usmHMAC128SHA224AuthProtocol,
    V3AuthProto.SHA256: usmHMAC192SHA256AuthProtocol,
    V3AuthProto.SHA384: usmHMAC256SHA384AuthProtocol,
    V3AuthProto.SHA512: usmHMAC384SHA512AuthProtocol,
}

_PRIV_PROTO_MAP = {
    V3PrivProto.DES:    usmDESPrivProtocol,
    V3PrivProto.DES3:   usmDESPrivProtocol,
    V3PrivProto.AES:    usmAesCfb128Protocol,
    V3PrivProto.AES128: usmAesCfb128Protocol,
    V3PrivProto.AES192: usmAesCfb192Protocol,
    V3PrivProto.AES256: usmAesCfb256Protocol,
}

# OID de probe : sysObjectID — universel, léger, répond toujours si SNMP actif
_PROBE_OID = "1.3.6.1.2.1.1.2.0"

# Valeurs sentinelles de fin de MIB retournées par pysnmp
_MIB_END_VALUES = frozenset({
    "No more variables left in this MIB View",
    "No Such Object currently exists at this OID",
    "No Such Instance currently exists at this OID",
})


# ---------------------------------------------------------------------------
# Exception publique
# ---------------------------------------------------------------------------

class SnmpError(Exception):
    """Levée sur tout échec SNMP (timeout, erreur PDU, OID inexistant…)."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_auth_data(credentials: SnmpCredentials) -> Any:
    """Convertit les credentials internes en objet pysnmp."""
    if isinstance(credentials, SnmpV1V2Credentials):
        mp_model = 0 if credentials.version == SnmpVersion.V1 else 1
        return CommunityData(credentials.community, mpModel=mp_model)

    creds = credentials
    auth_proto = (
        _AUTH_PROTO_MAP.get(creds.auth_proto, usmNoAuthProtocol)
        if creds.auth_proto else usmNoAuthProtocol
    )
    priv_proto = (
        _PRIV_PROTO_MAP.get(creds.priv_proto, usmNoPrivProtocol)
        if creds.priv_proto else usmNoPrivProtocol
    )
    return UsmUserData(
        creds.username,
        authKey=creds.auth_pass or "",
        privKey=creds.priv_pass or "",
        authProtocol=auth_proto,
        privProtocol=priv_proto,
    )


def _build_transport(ip: str, port: int, timeout: int, retries: int) -> Any:
    """Construit un UdpTransportTarget (objet non réutilisable en v6)."""
    return UdpTransportTarget((ip, port), timeout=timeout, retries=retries)


def _oid_is_subtree(base_oid: str, candidate_oid: str) -> bool:
    """Retourne True si candidate_oid appartient à la sous-arborescence base_oid."""
    return candidate_oid.startswith(base_oid.rstrip(".") + ".")


# ---------------------------------------------------------------------------
# Implémentations async — GET
# ---------------------------------------------------------------------------

async def _get_v6(auth, ip: str, port: int, timeout: int, retries: int,
                  *oids: str) -> dict[str, str]:
    """
    GET pour pysnmp 6.x.

    Crée un SnmpEngine neuf à chaque appel pour éviter le deadlock
    dû à la réutilisation d'un engine attaché à une event loop détruite.
    """
    engine    = SnmpEngine()   # ← NEUF à chaque appel, pas de réutilisation
    transport = _build_transport(ip, port, timeout, retries)
    object_types = [ObjectType(ObjectIdentity(oid)) for oid in oids]

    error_indication, error_status, error_index, var_binds = await getCmd(
        engine, auth, transport, ContextData(), *object_types
    )

    if error_indication:
        raise SnmpError(f"GET failed on {ip}: {error_indication}")
    if error_status:
        raise SnmpError(
            f"GET error on {ip}: {error_status.prettyPrint()} "
            f"at index {error_index}"
        )
    return {str(vb[0]): vb[1].prettyPrint() for vb in var_binds}


async def _get_v5(auth, transport, *oids: str) -> dict[str, str]:
    """GET pour pysnmp ≤ 5.x — getCmd est un générateur async."""
    engine = SnmpEngine()
    object_types = [ObjectType(ObjectIdentity(oid)) for oid in oids]
    async for error_indication, error_status, error_index, var_binds in getCmd(
        engine, auth, transport, ContextData(), *object_types
    ):
        if error_indication:
            raise SnmpError(f"GET failed: {error_indication}")
        if error_status:
            raise SnmpError(f"GET error: {error_status.prettyPrint()} at {error_index}")
        return {str(vb[0]): vb[1].prettyPrint() for vb in var_binds}
    return {}


# ---------------------------------------------------------------------------
# Implémentations async — WALK
# ---------------------------------------------------------------------------

async def _walk_v6(
    auth, ip: str, port: int, timeout: int, retries: int,
    oid: str, max_repetitions: int,
) -> list[tuple[str, str]]:
    """
    WALK pour pysnmp 6.x.

    nextCmd() est appelé en boucle, un pas à la fois.
    Chaque appel retourne un var_bind_table qui est une liste 2D :
      [ [ObjectType(oid, val)], [ObjectType(oid2, val2)], ... ]

    Un SnmpEngine neuf est créé à chaque itération pour éviter le deadlock
    d'event loop (même raison que pour _get_v6).

    lexicographicMode=False indique à pysnmp de s'arrêter automatiquement
    quand il sort de la sous-arborescence demandée — filet de sécurité
    en complément de notre vérification manuelle _oid_is_subtree().
    """
    results: list[tuple[str, str]] = []
    current_oid = oid

    while True:
        engine    = SnmpEngine()   # ← NEUF à chaque itération
        transport = _build_transport(ip, port, timeout, retries)

        try:
            error_indication, error_status, error_index, var_bind_table = await nextCmd(
                engine, auth, transport, ContextData(),
                ObjectType(ObjectIdentity(current_oid)),
                lexicographicMode=False,   # s'arrête en fin d'arborescence
            )
        except Exception as exc:
            logger.debug("Walk interrupted on %s: %s", ip, exc)
            break

        if error_indication:
            logger.debug("Walk on %s stopped: %s", ip, error_indication)
            break

        if error_status:
            raise SnmpError(
                f"Walk error on {ip}: {error_status.prettyPrint()} "
                f"at index {error_index}"
            )

        if not var_bind_table:
            break

        # var_bind_table est un tableau 2D : [ [ObjectType(oid, val)], ... ]
        # On itère sur les lignes et on extrait row[0] pour chaque ligne.
        for row in var_bind_table:
            var_bind    = row[0]                  # ObjectType de cette ligne
            returned_oid = str(var_bind[0])
            returned_val = var_bind[1].prettyPrint()

            # Sorti de la sous-arborescence → arrêt
            if not _oid_is_subtree(oid, returned_oid):
                return results

            # Sentinelle de fin de MIB → arrêt
            if returned_val in _MIB_END_VALUES:
                return results

            results.append((returned_oid, returned_val))
            current_oid = returned_oid   # avance le curseur pour le prochain appel

    return results


async def _walk_v5(
    auth, transport, oid: str, max_repetitions: int
) -> list[tuple[str, str]]:
    """WALK pour pysnmp ≤ 5.x — bulkCmd/nextCmd est un générateur async."""
    engine  = SnmpEngine()
    results: list[tuple[str, str]] = []

    _cmd   = bulkCmd if bulkCmd is not None else nextCmd
    _extra = (0, max_repetitions) if bulkCmd is not None else ()

    async for error_indication, error_status, error_index, var_binds in _cmd(
        engine, auth, transport, ContextData(),
        *_extra,
        ObjectType(ObjectIdentity(oid)),
        lexicographicMode=False,
    ):
        if error_indication:
            logger.debug("Walk interrupted: %s", error_indication)
            break
        if error_status:
            raise SnmpError(
                f"Walk error: {error_status.prettyPrint()} at index {error_index}"
            )
        for var_bind in var_binds:
            results.append((str(var_bind[0]), var_bind[1].prettyPrint()))

    return results


# ---------------------------------------------------------------------------
# Client public
# ---------------------------------------------------------------------------

class SnmpClient:
    """
    Client SNMP synchrone pour un hôte cible unique.

    Thread-safe : chaque appel public (get, walk, probe) crée sa propre
    event loop via asyncio.run() et un SnmpEngine neuf — il n'y a donc
    aucun état partagé entre les appels.

    Args:
        ip:          Adresse IP de la cible.
        credentials: Instance :class:`~orion_scanner.models.SnmpCredentials`.
        timeout:     Timeout par requête en secondes (défaut : 2).
        retries:     Nombre de tentatives en cas de timeout (défaut : 1).
    """

    def __init__(
        self,
        ip: str,
        credentials: SnmpCredentials,
        timeout: int = 2,
        retries: int = 1,
    ) -> None:
        self.ip          = ip
        self.credentials = credentials
        self.timeout     = timeout
        self.retries     = retries

        # PAS de self._engine ici — créé à la volée dans chaque coroutine
        self._auth_data = _build_auth_data(credentials)
        self._port = (
            credentials.port
            if isinstance(credentials, (SnmpV1V2Credentials, SnmpV3Credentials))
            else 161
        )

    # ------------------------------------------------------------------
    # API publique synchrone
    # ------------------------------------------------------------------

    def probe(self) -> bool:
        """
        Vérifie en un seul GET si l'hôte répond au SNMP.

        Teste sysObjectID (1.3.6.1.2.1.1.2.0) — OID universel présent
        sur tous les équipements SNMP.  Retourne False sur timeout ou
        erreur d'authentification (communauté incorrecte, etc.).

        Returns:
            True si l'hôte répond, False sinon.
        """
        try:
            result = self.get(_PROBE_OID)
            return bool(result)
        except SnmpError:
            return False
        except Exception:
            return False

    def get(self, *oids: str) -> dict[str, str]:
        """
        SNMP GET sur un ou plusieurs OIDs.

        Returns:
            ``{oid_str: valeur_str}``

        Raises:
            :class:`SnmpError`
        """
        return asyncio.run(self._async_get(*oids))

    def walk(self, oid: str, max_repetitions: int = 25) -> list[tuple[str, str]]:
        """
        SNMP WALK à partir d'un OID racine.

        Returns:
            Liste de tuples ``(oid_str, valeur_str)``.

        Raises:
            :class:`SnmpError`
        """
        return asyncio.run(self._async_walk(oid, max_repetitions))

    # ------------------------------------------------------------------
    # Dispatch async selon version API
    # ------------------------------------------------------------------

    async def _async_get(self, *oids: str) -> dict[str, str]:
        if _APIV6:
            return await _get_v6(
                self._auth_data,
                self.ip, self._port, self.timeout, self.retries,
                *oids,
            )
        else:
            transport = _build_transport(self.ip, self._port, self.timeout, self.retries)
            return await _get_v5(self._auth_data, transport, *oids)

    async def _async_walk(self, oid: str, max_repetitions: int) -> list[tuple[str, str]]:
        if _APIV6:
            return await _walk_v6(
                self._auth_data,
                self.ip, self._port, self.timeout, self.retries,
                oid, max_repetitions,
            )
        else:
            transport = _build_transport(self.ip, self._port, self.timeout, self.retries)
            return await _walk_v5(self._auth_data, transport, oid, max_repetitions)
