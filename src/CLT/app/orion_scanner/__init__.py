"""
Orion Scanner — SNMP-based network discovery tool.

Scans a subnet via SNMP and populates the Orion database with:
  - Device inventory (System MIB)
  - Interface list (IF-MIB)
  - IP address table (IP-MIB)
  - L2 topology (LLDP / CDP)
"""

__version__ = "0.1.0"
