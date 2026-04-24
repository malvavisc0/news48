"""Shared security utilities for URL validation and input sanitization."""

import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Private/reserved IP ranges that must not be fetched.
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),  # AWS metadata / link-local
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 private
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]

# Hostnames that are always blocked.
_BLOCKED_HOSTNAMES = frozenset(
    {
        "metadata.google.internal",
        "instance-data",
        "localhost",
    }
)


def validate_url_not_private(url: str) -> None:
    """Validate that a URL does not resolve to a private/reserved IP.

    Raises ValueError if the URL targets a blocked network or hostname.
    This prevents SSRF attacks via the agent fetch tools.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname

    if not hostname:
        raise ValueError(f"URL has no hostname: {url}")

    # Check blocked hostnames
    if hostname.lower() in _BLOCKED_HOSTNAMES:
        raise ValueError(f"URL hostname '{hostname}' is blocked (metadata/internal)")

    # Resolve hostname to IP and check against blocked networks
    try:
        addr_info = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        for _family, _type, _proto, _canonname, sockaddr in addr_info:
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue

            for network in _BLOCKED_NETWORKS:
                if ip in network:
                    raise ValueError(
                        f"URL '{url}' resolves to blocked "
                        f"network: {ip} (in {network})"
                    )
    except socket.gaierror:
        raise ValueError(f"Cannot resolve hostname: {hostname}")


def escape_like(value: str) -> str:
    """Escape SQL LIKE wildcard characters in a value.

    Escapes |, %, and _ so they are treated as literals in LIKE patterns.
    Uses ``|`` as the ESCAPE character (cross-database safe; pair with
    ``ESCAPE '|'`` in every LIKE clause).
    """
    return value.replace("|", "||").replace("%", "|%").replace("_", "|_")
