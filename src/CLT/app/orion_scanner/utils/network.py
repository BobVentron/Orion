"""
Network utilities for Orion Scanner.

Handles subnet parsing and host address generation using netaddr.
"""

from collections.abc import Iterator

import netaddr


def iter_hosts(subnet: str, exclude: list[str] | None = None) -> Iterator[str]:
    """
    Yield every usable host address in *subnet*, skipping excluded IPs.

    Args:
        subnet: A CIDR notation string (e.g. ``"192.168.1.0/24"``).
        exclude: Optional list of IP address strings to skip.

    Yields:
        Host IP addresses as strings.

    Raises:
        netaddr.AddrFormatError: If *subnet* is not a valid CIDR notation.

    Example::

        for ip in iter_hosts("10.0.0.0/30", exclude=["10.0.0.1"]):
            print(ip)
        # 10.0.0.2
    """
    excluded: set[netaddr.IPAddress] = set()
    if exclude:
        for raw in exclude:
            try:
                excluded.add(netaddr.IPAddress(raw.strip()))
            except netaddr.AddrFormatError:
                pass  # silently skip malformed exclusions

    network = netaddr.IPNetwork(subnet)
    for host in network.iter_hosts():
        if host not in excluded:
            yield str(host)


def validate_cidr(value: str) -> str:
    """
    Return *value* unchanged if it is a valid CIDR prefix, raise otherwise.

    Args:
        value: String to validate.

    Returns:
        The original *value* string.

    Raises:
        ValueError: If *value* is not a valid CIDR notation.
    """
    try:
        netaddr.IPNetwork(value)
    except (netaddr.AddrFormatError, ValueError) as exc:
        raise ValueError(f"'{value}' is not a valid CIDR prefix.") from exc
    return value
