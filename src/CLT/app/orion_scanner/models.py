"""
Domain models for Orion Scanner.

Pure dataclasses — no ORM dependency — representing the data collected
during a SNMP scan session.  These are later consumed by ``db.writer``
to persist results.
"""

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Enums (mirror DB enum types)
# ---------------------------------------------------------------------------


class SnmpVersion(str, Enum):
    V1 = "v1"
    V2C = "v2c"
    V3 = "v3"


class V3Level(str, Enum):
    NO_AUTH_NO_PRIV = "noAuthNoPriv"
    AUTH_NO_PRIV = "authNoPriv"
    AUTH_PRIV = "authPriv"


class V3AuthProto(str, Enum):
    MD5 = "MD5"
    SHA = "SHA"
    SHA224 = "SHA224"
    SHA256 = "SHA256"
    SHA384 = "SHA384"
    SHA512 = "SHA512"


class V3PrivProto(str, Enum):
    DES = "DES"
    DES3 = "3DES"
    AES = "AES"
    AES128 = "AES128"
    AES192 = "AES192"
    AES256 = "AES256"


class IfAdminStatus(str, Enum):
    UP = "Up"
    DOWN = "Down"


class IfOperStatus(str, Enum):
    UP = "Up"
    DOWN = "Down"


class LldpProtocol(str, Enum):
    LLDP = "LLDP"
    CDP = "CDP"


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


@dataclass
class SnmpV1V2Credentials:
    """Community-string credentials for SNMP v1 or v2c."""

    version: SnmpVersion
    community: str
    port: int = 161


@dataclass
class SnmpV3Credentials:
    """Full SNMPv3 USM credentials."""

    username: str
    level: V3Level
    auth_proto: V3AuthProto | None = None
    auth_pass: str | None = None
    priv_proto: V3PrivProto | None = None
    priv_pass: str | None = None
    port: int = 161


SnmpCredentials = SnmpV1V2Credentials | SnmpV3Credentials


# ---------------------------------------------------------------------------
# Scan configuration
# ---------------------------------------------------------------------------


@dataclass
class ScanTarget:
    """A single subnet to scan with its associated credentials."""

    subnet: str
    credentials: SnmpCredentials
    exclude_ips: list[str] = field(default_factory=list)
    timeout: int = 2
    retries: int = 1


# ---------------------------------------------------------------------------
# Collected SNMP data
# ---------------------------------------------------------------------------


@dataclass
class SystemInfo:
    """Data collected from MIB-II System group (RFC 1213)."""

    ip: str
    sys_name: str | None = None
    sys_descr: str | None = None
    sys_object_id: str | None = None
    sys_location: str | None = None
    sys_contact: str | None = None
    sys_uptime_centiseconds: int | None = None


@dataclass
class InterfaceInfo:
    """One row from IF-MIB ifTable / ifXTable."""

    if_index: int
    name: str | None = None
    description: str | None = None
    alias: str | None = None
    mac_address: str | None = None
    if_type: str | None = None
    mtu: int | None = None
    speed_bps: int | None = None
    admin_status: IfAdminStatus | None = None
    oper_status: IfOperStatus | None = None


@dataclass
class IpAddressInfo:
    """One row from IP-MIB ipAddrTable."""

    address: str
    netmask: str
    if_index: int


@dataclass
class LldpNeighbor:
    """One entry from LLDP-MIB lldpRemTable (or CDP equivalent)."""

    local_if_index: int
    remote_chassis_id: str | None = None
    remote_sys_name: str | None = None
    remote_port_id: str | None = None
    remote_mgmt_ip: str | None = None
    protocol: LldpProtocol = LldpProtocol.LLDP


@dataclass
class PhysicalEntityInfo:
    """
    One row from ENTITY-MIB entPhysicalTable (RFC 6933).

    Covers chassis, modules, ports, fans, power supplies, etc.
    ``ent_index`` is the SNMP table index (entPhysicalIndex).
    ``parent_index`` maps to entPhysicalContainedIn (0 = root).
    """

    ent_index: int
    name: str
    description: str | None = None
    physical_class: str | None = None   # chassis, module, port, fan, powerSupply…
    serial_number: str | None = None
    part_number: str | None = None      # entPhysicalModelName
    firmware_version: str | None = None # entPhysicalSoftwareRev
    parent_index: int = 0
    is_fru: bool = False                # Field Replaceable Unit


@dataclass
class VlanInfo:
    """
    One VLAN entry collected via Q-BRIDGE-MIB or CISCO-VTP-MIB.

    ``vlan_tag`` is the 802.1Q tag (1–4094).
    ``role`` and ``status`` are normalised to the DB enum values.
    """

    vlan_tag: int
    name: str | None = None
    status: str = "Active"      # Active | Suspended
    type: str = "Ethernet"      # Ethernet | FDDI …
    role: str = "Data"          # Data | Voice | Management | Guest | Blackhole


@dataclass
class DeviceScanResult:
    """Aggregated scan result for a single device (one IP)."""

    ip: str
    credentials_used: SnmpCredentials
    system: SystemInfo | None = None
    interfaces: list[InterfaceInfo] = field(default_factory=list)
    ip_addresses: list[IpAddressInfo] = field(default_factory=list)
    lldp_neighbors: list[LldpNeighbor] = field(default_factory=list)
    physical_entities: list[PhysicalEntityInfo] = field(default_factory=list)
    vlans: list[VlanInfo] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        """Return True if at least system info was collected."""
        return self.system is not None


@dataclass
class InterfaceStatusCheck:
    """Statut courant d'une interface (check léger, sans walk complet)."""

    if_index: int
    admin_status: IfAdminStatus | None = None
    oper_status:  IfOperStatus  | None = None
    speed_bps:    int | None = None


@dataclass
class MacTableEntry:
    """Une entrée de la table FDB d'un switch."""

    mac_address: str
    if_index:    int
    bridge_port: int
    entry_type:  str = "Dynamic"   # Dynamic | Static | Self


@dataclass
class CheckResult:
    """Résultat d'un check récurrent sur un device déjà connu en base."""

    device_id: str                                  # UUID du device en base
    ip: str
    interface_statuses: list[InterfaceStatusCheck] = field(default_factory=list)
    mac_entries:        list[MacTableEntry]         = field(default_factory=list)
    lldp_neighbors:     list[LldpNeighbor]          = field(default_factory=list)
    errors:             list[str]                   = field(default_factory=list)

    @property
    def is_reachable(self) -> bool:
        return not any("probe failed" in e for e in self.errors)
