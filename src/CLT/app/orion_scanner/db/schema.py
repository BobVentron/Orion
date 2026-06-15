"""
SQLAlchemy ORM — miroir exact du DDL Orion (Orion_SQL.sql).

Seules les tables **écrites par le scanner** sont définies ici en tant que
classes ORM complètes.  Les tables de référence peuplées manuellement (vendors,
device_categories…) sont déclarées en tant que stubs minimaux suffisant pour
que les FK résolvent correctement.

Conventions
-----------
- Les noms de table et de colonne reproduisent exactement le DDL SQL.
- ``devices.id`` est un UUID généré par PostgreSQL (``gen_random_uuid()``).
- Les champs ``NOT NULL`` sans valeur par défaut sont marqués ``nullable=False``.
- Les contraintes CHECK du DDL ne sont pas redéclarées côté ORM (elles existent
  déjà en base ; les lever ici ne ferait que dupliquer la logique).
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import CIDR, INET, MACADDR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ===========================================================================
# SECTION 1 — Credentials & Profiles
# ===========================================================================


class AuthSnmp(Base):
    __tablename__ = "auth_snmp"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(10), nullable=False, default="v2c")
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=161)
    community: Mapped[str | None] = mapped_column(String(255))
    v3_user: Mapped[str | None] = mapped_column(String(100))
    v3_level: Mapped[str | None] = mapped_column(String(20))
    v3_auth_proto: Mapped[str | None] = mapped_column(String(20))
    v3_auth_pass: Mapped[str | None] = mapped_column(String(255))
    v3_priv_proto: Mapped[str | None] = mapped_column(String(20))
    v3_priv_pass: Mapped[str | None] = mapped_column(String(255))


class AuthCli(Base):
    __tablename__ = "auth_cli"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    password: Mapped[str | None] = mapped_column(String(255))
    enable_password: Mapped[str | None] = mapped_column(String(255))
    ssh_key_path: Mapped[str | None] = mapped_column(String(255))
    protocol_pref: Mapped[str] = mapped_column(String(10), nullable=False, default="SSH")
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=22)


class AuthProfile(Base):
    __tablename__ = "auth_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    snmp_id: Mapped[int | None] = mapped_column(ForeignKey("auth_snmp.id", ondelete="SET NULL"))
    cli_id: Mapped[int | None] = mapped_column(ForeignKey("auth_cli.id", ondelete="SET NULL"))

    snmp: Mapped[AuthSnmp | None] = relationship("AuthSnmp", lazy="joined")
    cli: Mapped[AuthCli | None] = relationship("AuthCli", lazy="joined")


# ===========================================================================
# SECTION 19 — Scan Networks & Profiles
# ===========================================================================


class ScanProfile(Base):
    """Stratégie technique de scan (timeout, threads, type, intervalle)."""

    __tablename__ = "scan_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    concurrency_threads: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    packet_delay_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ScanNetwork(Base):
    """
    Réseau cible à surveiller.

    Scheduling via next_scan_at :
      NULL          → jamais scanné, scan immédiat
      <= NOW()      → heure du prochain scan atteinte, scan autorisé
      >  NOW()      → trop tôt, le daemon skip
      interval = 0  → scan unique, next_scan_at reste NULL après
    """

    __tablename__ = "scan_networks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subnet: Mapped[str] = mapped_column(CIDR, nullable=False, unique=True)
    exclude_ips: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(String(255))

    scan_profile_id: Mapped[int] = mapped_column(
        ForeignKey("scan_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    auth_profile_id: Mapped[int] = mapped_column(
        ForeignKey("auth_profiles.id", ondelete="RESTRICT"), nullable=False
    )

    next_scan_at: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)

    last_scan_status: Mapped[str] = mapped_column(String(20), nullable=False, default="idle")
    last_scan_at: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    last_scan_duration: Mapped[int | None] = mapped_column(Integer)
    last_hosts_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)

    scan_profile: Mapped[ScanProfile] = relationship("ScanProfile", lazy="joined")
    auth_profile: Mapped[AuthProfile] = relationship("AuthProfile", lazy="joined")

    __table_args__ = (
        UniqueConstraint("subnet", "auth_profile_id", name="uq_scan_network_subnet_profile"),
    )


# ===========================================================================
# SECTION 3 — Dictionnaire & Normalisation
# ===========================================================================


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)


class VendorIanaPen(Base):
    """Mapping numéro PEN IANA → Vendor (identifie le constructeur via sysObjectID)."""

    __tablename__ = "vendor_iana_pen"

    pen: Mapped[int] = mapped_column(Integer, primary_key=True)
    vendor_id: Mapped[int] = mapped_column(
        ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False
    )


class VendorOui(Base):
    """Mapping OUI MAC (6 hex sans séparateur) → Vendor."""

    __tablename__ = "vendor_oui"

    mac_prefix: Mapped[str] = mapped_column(String(6), primary_key=True)
    vendor_id: Mapped[int] = mapped_column(
        ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False
    )


class DeviceCategory(Base):
    __tablename__ = "device_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    icon_class: Mapped[str | None] = mapped_column(String(100))


class DeviceFamily(Base):
    __tablename__ = "device_families"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor_id: Mapped[int] = mapped_column(
        ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("device_categories.id", ondelete="SET NULL"), nullable=False
    )
    sysobject_oid: Mapped[str | None] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class DeviceModel(Base):
    """
    Catalogue des modèles matériels.

    Le scanner crée automatiquement un modèle générique (``part_number='UNKNOWN'``)
    lié à une famille générique quand l'OID de l'équipement n'est pas reconnu.
    Cela permet de satisfaire la contrainte NOT NULL sur ``devices.model_id``.
    """

    __tablename__ = "device_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(
        ForeignKey("device_families.id", ondelete="CASCADE"), nullable=False
    )
    part_number: Mapped[str] = mapped_column(String(100), nullable=False)
    is_rackable: Mapped[bool] = mapped_column(Boolean, default=True)
    u_height: Mapped[int] = mapped_column(Integer, default=1)
    is_eol: Mapped[bool] = mapped_column(Boolean, default=False)


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL")
    )


class Rack(Base):
    __tablename__ = "racks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    height_u: Mapped[int] = mapped_column(Integer, nullable=False, default=42)
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )


# ===========================================================================
# SECTION 4 — Inventaire physique
# ===========================================================================


class RefDeviceStatus(Base):
    __tablename__ = "ref_device_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str | None] = mapped_column(String(7), default="#6c757d")
    is_monitored: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text)


class Firmware(Base):
    __tablename__ = "firmwares"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    release_date: Mapped[str | None] = mapped_column(String(20))
    is_reference: Mapped[bool] = mapped_column(Boolean, default=False)


class Device(Base):
    """
    Équipement réseau unique.

    ``id`` est un UUID généré côté Python (``uuid.uuid4()``), compatible avec
    le ``gen_random_uuid()`` PostgreSQL du DDL.

    Contraintes NOT NULL du DDL à respecter impérativement :
    - ``hostname``   → sysName SNMP, ou l'IP si absent
    - ``model_id``   → résolu via sysObjectID, ou modèle générique 'UNKNOWN'
    - ``status_id``  → toujours 'provisioning' à la création
    """

    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(100))
    snmp_contact: Mapped[str | None] = mapped_column(String(255))
    snmp_description: Mapped[str | None] = mapped_column(Text)

    # FK obligatoires (NOT NULL en base)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("device_models.id", ondelete="RESTRICT"), nullable=False
    )
    status_id: Mapped[int] = mapped_column(
        ForeignKey("ref_device_status.id", ondelete="RESTRICT"), nullable=False
    )

    # FK optionnelles
    firmware_id: Mapped[int | None] = mapped_column(
        ForeignKey("firmwares.id", ondelete="SET NULL")
    )
    auth_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_profiles.id", ondelete="SET NULL")
    )
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL")
    )
    racks_id: Mapped[int | None] = mapped_column(
        ForeignKey("racks.id", ondelete="SET NULL")
    )
    rack_position: Mapped[int | None] = mapped_column(Integer)

    # Activée après Section 5 dans le DDL ; on ne déclare pas la FK ORM
    # pour éviter une circular dependency au moment du flush.
    int_mgmt: Mapped[int | None] = mapped_column(BigInteger)

    interfaces: Mapped[list[Interface]] = relationship(
        "Interface",
        back_populates="device",
        cascade="all, delete-orphan",
    )
    device_status: Mapped[DeviceStatus | None] = relationship(
        "DeviceStatus",
        back_populates="device",
        uselist=False,
        cascade="all, delete-orphan",
    )


class DeviceStatus(Base):
    """Snapshot temps réel de la joignabilité d'un équipement."""

    __tablename__ = "device_status"

    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        primary_key=True,
    )
    last_poll: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    icmp_status: Mapped[str | None] = mapped_column(String(20))
    snmp_status: Mapped[str | None] = mapped_column(String(20))
    uptime_seconds: Mapped[int | None] = mapped_column(BigInteger)

    device: Mapped[Device] = relationship("Device", back_populates="device_status")


class DeviceModule(Base):
    """Composants physiques remontés via ENTITY-MIB (chassis, PSU, fan…)."""

    __tablename__ = "device_modules"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    ent_index: Mapped[int | None] = mapped_column(Integer)
    parent_index: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("device_modules.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # 'class' est un mot réservé Python — on utilise class_ et mappe sur 'class'
    class_: Mapped[str | None] = mapped_column("class", String(50))
    serial_number: Mapped[str | None] = mapped_column(String(100))
    part_number: Mapped[str | None] = mapped_column(String(100))
    is_fru: Mapped[bool] = mapped_column(Boolean, default=False)


# ===========================================================================
# SECTION 5 — Interfaces & Connectivité L2
# ===========================================================================


class Interface(Base):
    __tablename__ = "interfaces"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    if_index: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    alias: Mapped[str | None] = mapped_column(String(255))
    mac_address: Mapped[str | None] = mapped_column(MACADDR)
    type: Mapped[str | None] = mapped_column(String(50))
    mtu: Mapped[int | None] = mapped_column(Integer)
    speed: Mapped[int | None] = mapped_column(BigInteger)

    device: Mapped[Device] = relationship("Device", back_populates="interfaces")
    statuses: Mapped[list[InterfaceStatus]] = relationship(
        "InterfaceStatus",
        cascade="all, delete-orphan",
    )
    ip_maps: Mapped[list[IpInterfaceMap]] = relationship(
        "IpInterfaceMap",
        cascade="all, delete-orphan",
    )
    lldp_neighbors: Mapped[list[LldpNeighbor]] = relationship(
        "LldpNeighbor",
        back_populates="local_interface",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        # Garantit l'unicité de (device, ifIndex) pour les upserts
        Index("uq_interface_device_ifindex", "device_id", "if_index", unique=True),
    )


class IpInterfaceMap(Base):
    """Lien N-N entre interfaces et adresses IP."""

    __tablename__ = "ip_interface_map"

    interface_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("interfaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    ip_address_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ip_addresses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_virtual: Mapped[bool] = mapped_column(Boolean, default=False)
    label: Mapped[str | None] = mapped_column(String(100))


class InterfaceStatus(Base):
    """
    Historique des changements d'état d'une interface.

    Table append-only : chaque scan insère une nouvelle ligne.
    La PK composite (interface_id, last_change) empêche les doublons
    si le scanner tourne deux fois dans la même seconde.
    """

    __tablename__ = "interfaces_status"

    interface_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("interfaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    last_change: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        server_default=func.now(),
    )
    admin_status: Mapped[str] = mapped_column(String(10), nullable=False)
    oper_status: Mapped[str] = mapped_column(String(10), nullable=False)


class LldpNeighbor(Base):
    """
    Voisin L2 découvert via LLDP ou CDP.

    ``remote_ip`` est stocké en VARCHAR(50) dans le DDL (pas une FK vers
    ip_addresses) — on écrit l'IP brute remontée par le MIB.
    """

    __tablename__ = "lldp_neighbors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    local_interface_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("interfaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    remote_chassis_id: Mapped[str | None] = mapped_column(String(255))
    remote_sysname: Mapped[str | None] = mapped_column(String(255))
    remote_port_id: Mapped[str | None] = mapped_column(String(255))
    remote_ip: Mapped[str | None] = mapped_column(String(50))
    protocol: Mapped[str] = mapped_column(String(10), nullable=False, default="LLDP")
    last_seen: Mapped[str | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    local_interface: Mapped[Interface] = relationship(
        "Interface", back_populates="lldp_neighbors"
    )

    __table_args__ = (
        UniqueConstraint(
            "local_interface_id",
            "remote_sysname",
            "remote_port_id",
            "protocol",
            name="uq_lldp_neighbor",
        ),
    )


class Vlan(Base):
    __tablename__ = "vlans"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    vlan_tag: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="Active")
    type: Mapped[str] = mapped_column(String(20), default="Ethernet")
    role: Mapped[str] = mapped_column(String(20), default="Data")

    __table_args__ = (
        UniqueConstraint("device_id", "vlan_tag", name="uq_vlan_device_tag"),
    )


# ===========================================================================
# SECTION 6 — Layer 3 & IPAM
# ===========================================================================


class Vrf(Base):
    __tablename__ = "vrfs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rd: Mapped[str | None] = mapped_column(String(100))


class IpSubnet(Base):
    __tablename__ = "ip_subnets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prefix: Mapped[str] = mapped_column(CIDR, nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(String(100))
    vrf_global_id: Mapped[int | None] = mapped_column(
        ForeignKey("vrfs.id", ondelete="SET NULL")
    )
    vlan_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("vlans.id", ondelete="SET NULL")
    )
    usage_percent: Mapped[int] = mapped_column(Integer, default=0)


class IpAddress(Base):
    __tablename__ = "ip_addresses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    address: Mapped[str] = mapped_column(INET, nullable=False, unique=True)
    subnet_id: Mapped[int | None] = mapped_column(
        ForeignKey("ip_subnets.id", ondelete="CASCADE")
    )
    dns_name: Mapped[str | None] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(20), default="Static")
    status: Mapped[str] = mapped_column(String(20), default="Active")
    last_seen: Mapped[str | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ===========================================================================
# SECTION 5b — Topologie & FDB
# ===========================================================================


class MacAddressEntry(Base):
    """Entrée de la table FDB (Forwarding Database) d'un switch."""

    __tablename__ = "mac_address_table"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    interface_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("interfaces.id", ondelete="CASCADE"), nullable=False
    )
    mac_address: Mapped[str] = mapped_column(MACADDR, nullable=False)
    type: Mapped[str] = mapped_column(String(20), default="Dynamic")
    last_seen: Mapped[str | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("interface_id", "mac_address", name="uq_mac_fdb_entry"),
    )


class InterfaceVlan(Base):
    """Appartenance d'une interface à un VLAN (port membership)."""

    __tablename__ = "interface_vlans"

    interface_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("interfaces.id", ondelete="CASCADE"), primary_key=True
    )
    vlan_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("vlans.id", ondelete="CASCADE"), primary_key=True
    )
    mode: Mapped[str] = mapped_column(String(20), default="Untagged")
    is_native: Mapped[bool] = mapped_column(Boolean, default=False)


class NetworkLink(Base):
    """
    Lien physique ou logique entre deux interfaces.

    Normalisation : src_interface_id < dst_interface_id
    Ce invariant garantit qu'un lien A↔B et B↔A sont la même ligne en base,
    quelque soit le sens de découverte (LLDP sur A ou sur B).
    La contrainte UNIQUE sur (src, dst) s'appuie sur cet ordre.
    """

    __tablename__ = "network_links"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    src_interface_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("interfaces.id", ondelete="CASCADE"), nullable=False
    )
    dst_interface_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("interfaces.id", ondelete="CASCADE"), nullable=False
    )
    discovery_proto: Mapped[str] = mapped_column(String(20), default="LLDP")
    link_type: Mapped[str] = mapped_column(String(50), default="Copper")
    media_subtype: Mapped[str | None] = mapped_column(String(50))
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen: Mapped[str | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("src_interface_id", "dst_interface_id", name="uq_network_link"),
    )


# ===========================================================================
# SECTION — Monitoring récurrent
# ===========================================================================

class MonitoringProfile(Base):
    """Profil de monitoring récurrent (prérempli par Orion_DATA_monitoring.sql)."""
    __tablename__ = "monitoring_profiles"

    id:               Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    name:             Mapped[str]      = mapped_column(String(100), nullable=False, unique=True)
    scan_type:        Mapped[str]      = mapped_column(String(50),  nullable=False)
    interval_seconds: Mapped[int]      = mapped_column(Integer, nullable=False, default=300)
    timeout_ms:       Mapped[int]      = mapped_column(Integer, nullable=False, default=2000)
    retry_count:      Mapped[int]      = mapped_column(Integer, nullable=False, default=1)
    is_enabled:       Mapped[bool]     = mapped_column(Boolean, default=True)
    description:      Mapped[str|None] = mapped_column(Text)


class DeviceMonitoringTask(Base):
    """Tâche de monitoring récurrent pour un device donné."""
    __tablename__ = "device_monitoring_tasks"

    device_id:            Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True
    )
    profile_id:           Mapped[int]      = mapped_column(
        ForeignKey("monitoring_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    is_enabled:           Mapped[bool]     = mapped_column(Boolean, default=True)
    next_run_at:          Mapped[str|None] = mapped_column(DateTime(timezone=True))
    last_run_at:          Mapped[str|None] = mapped_column(DateTime(timezone=True))
    last_run_status:      Mapped[str]      = mapped_column(String(20), default="idle")
    consecutive_failures: Mapped[int]      = mapped_column(Integer, default=0)
    last_error:           Mapped[str|None] = mapped_column(Text)

    profile: Mapped[MonitoringProfile] = relationship("MonitoringProfile", lazy="joined")


# ===========================================================================
# SECTION — Métriques time-series
# ===========================================================================


class DeviceMetricsHistory(Base):
    """Snapshots CPU/RAM/temp/ICMP — append-only, une ligne par poll."""
    __tablename__ = "device_metrics_history"

    time:         Mapped[str]       = mapped_column(DateTime(timezone=True), primary_key=True)
    device_id:    Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True
    )
    cpu_load:     Mapped[int|None]   = mapped_column(Integer)
    ram_usage:    Mapped[int|None]   = mapped_column(Integer)
    ram_free:     Mapped[int|None]   = mapped_column(Integer)
    temp_celsius: Mapped[int|None]   = mapped_column(Integer)
    icmp_rtt:     Mapped[float|None] = mapped_column()
    icmp_loss:    Mapped[int|None]   = mapped_column(Integer)


class InterfaceMetricsHistory(Base):
    """Compteurs bruts IF-MIB — append-only, une ligne par poll par interface."""
    __tablename__ = "interface_metrics_history"

    time:               Mapped[str] = mapped_column(DateTime(timezone=True), primary_key=True)
    interface_id:       Mapped[int] = mapped_column(
        BigInteger, ForeignKey("interfaces.id", ondelete="CASCADE"), primary_key=True
    )
    in_octets:          Mapped[int|None] = mapped_column(BigInteger)
    out_octets:         Mapped[int|None] = mapped_column(BigInteger)
    in_ucast_pkts:      Mapped[int|None] = mapped_column(BigInteger)
    out_ucast_pkts:     Mapped[int|None] = mapped_column(BigInteger)
    in_nucast_pkts:     Mapped[int|None] = mapped_column(BigInteger)
    out_nucast_pkts:    Mapped[int|None] = mapped_column(BigInteger)
    in_errors:          Mapped[int|None] = mapped_column(Integer)
    out_errors:         Mapped[int|None] = mapped_column(Integer)
    in_discards:        Mapped[int|None] = mapped_column(Integer)
    out_discards:       Mapped[int|None] = mapped_column(Integer)
    in_unknown_protos:  Mapped[int|None] = mapped_column(Integer)
    in_bps:             Mapped[int|None] = mapped_column(BigInteger)
    out_bps:            Mapped[int|None] = mapped_column(BigInteger)
    consumption_w:      Mapped[float|None] = mapped_column()


# ===========================================================================
# SECTION — Redondance L3 / EtherChannel / Trunks
# ===========================================================================


class RedundancyState(Base):
    """Groupes HSRP/VRRP par interface."""
    __tablename__ = "redundancy_states"

    id:           Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    interface_id: Mapped[int]      = mapped_column(
        BigInteger, ForeignKey("interfaces.id", ondelete="CASCADE"), nullable=False
    )
    group_id:     Mapped[int]      = mapped_column(Integer, nullable=False)
    virtual_ip:   Mapped[str|None] = mapped_column(INET)
    state:        Mapped[str|None] = mapped_column(String(20))
    priority:     Mapped[int|None] = mapped_column(Integer)
    active_router: Mapped[str|None] = mapped_column(UUID(as_uuid=False))
    protocol:     Mapped[str]      = mapped_column(String(10), default="HSRP")
    preempt:      Mapped[bool]     = mapped_column(Boolean, default=False)
    hello_time:   Mapped[int|None] = mapped_column(Integer)
    hold_time:    Mapped[int|None] = mapped_column(Integer)
    last_change:  Mapped[str|None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("interface_id", "group_id", name="uq_redundancy_group"),
    )


class LagMember(Base):
    """Membres EtherChannel / LACP."""
    __tablename__ = "lag_members"

    id:                   Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    agg_interface_id:     Mapped[int]      = mapped_column(
        BigInteger, ForeignKey("interfaces.id", ondelete="CASCADE"), nullable=False
    )
    member_interface_id:  Mapped[int]      = mapped_column(
        BigInteger, ForeignKey("interfaces.id", ondelete="CASCADE"), nullable=False
    )
    protocol:             Mapped[str]      = mapped_column(String(20), default="LACP")
    actor_oper_key:       Mapped[int|None] = mapped_column(Integer)
    partner_oper_system:  Mapped[str|None] = mapped_column(String(100))
    is_synced:            Mapped[bool]     = mapped_column(Boolean, default=False)
    is_standby:           Mapped[bool]     = mapped_column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("agg_interface_id", "member_interface_id", name="uq_lag_member"),
    )


class InterfaceTrunk(Base):
    """Configuration trunk 802.1Q d'une interface."""
    __tablename__ = "interface_trunks"

    id:              Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    interface_id:    Mapped[int]      = mapped_column(
        BigInteger, ForeignKey("interfaces.id", ondelete="CASCADE"), nullable=False
    )
    encapsulation:   Mapped[str]      = mapped_column(String(20), default="dot1q")
    admin_status:    Mapped[str|None] = mapped_column(String(20))
    oper_status:     Mapped[str|None] = mapped_column(String(20))
    allowed_vlans:   Mapped[str|None] = mapped_column(Text)
    pruning_enabled: Mapped[bool]     = mapped_column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("interface_id", name="uq_trunk_interface"),
    )


# ===========================================================================
# SECTION — ARP, Routing, STP
# ===========================================================================


class ArpTable(Base):
    """Entrée de la table ARP (ipNetToMedia)."""
    __tablename__ = "arp_table"

    id:             Mapped[int]     = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    interface_id:   Mapped[int]     = mapped_column(BigInteger, ForeignKey("interfaces.id", ondelete="CASCADE"), nullable=False)
    ip_address_id:  Mapped[int]     = mapped_column(BigInteger, ForeignKey("ip_addresses.id", ondelete="CASCADE"), nullable=False)
    mac_address:    Mapped[str]     = mapped_column(MACADDR, nullable=False)
    last_seen:      Mapped[str|None] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("interface_id", "ip_address_id", name="uq_arp_entry"),
    )



class RoutingTable(Base):
    """Entrée de table de routage."""
    __tablename__ = "routing_table"

    id:           Mapped[int]      = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    vrf_id:       Mapped[int]      = mapped_column(ForeignKey("vrfs.id", ondelete="CASCADE"), nullable=False)
    interface_id: Mapped[int|None] = mapped_column(BigInteger, ForeignKey("interfaces.id", ondelete="CASCADE"))
    dest_net:     Mapped[str]      = mapped_column(CIDR, nullable=False)
    next_hop:     Mapped[str|None] = mapped_column(INET)
    protocol:     Mapped[str]      = mapped_column(String(20), default="static")
    metric:       Mapped[int]      = mapped_column(Integer, default=1)


class STPInstance(Base):
    """Instance STP (Spanning Tree) d'un device."""
    __tablename__ = "stp_instances"

    id:              Mapped[int]       = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id:       Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    vlan_id:         Mapped[int|None]  = mapped_column(BigInteger, ForeignKey("vlans.id", ondelete="CASCADE"))
    root_bridge_id:  Mapped[str|None]  = mapped_column(String(50))
    root_cost:       Mapped[int|None]  = mapped_column(Integer)
    bridge_priority: Mapped[int|None]  = mapped_column(Integer)


class STPInterfaceState(Base):
    """État STP d'une interface."""
    __tablename__ = "stp_interface_state"

    interface_id:    Mapped[int] = mapped_column(BigInteger, ForeignKey("interfaces.id", ondelete="CASCADE"), primary_key=True)
    stp_instance_id: Mapped[int] = mapped_column(ForeignKey("stp_instances.id", ondelete="CASCADE"), primary_key=True)
    timestamp:       Mapped[str|None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    state:           Mapped[str|None] = mapped_column(String(20))
    role:            Mapped[str|None] = mapped_column(String(20))