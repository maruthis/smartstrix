"""Reject hostnames and URLs that would let the backend fetch internal targets."""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

from fastapi import HTTPException, status


# At least one label plus a TLD — rejects localhost, bare IPs, and empty
# strings. Length cap is RFC 1035.
_HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata.goog",
    }
)


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or not ip.is_global
    )


def _host_from_input(hostname: str) -> str:
    """Accept a bare host or a pasted URL; return only the hostname.

    People paste ``https://app.example.com/`` into the add-domain field.
    The stored value is still a hostname — scheme, path, query, fragment,
    and port are dropped. Userinfo is rejected so ``user@host`` cannot be
    smuggled through as a URL.
    """
    value = hostname.strip()
    if not value:
        return ""
    if value.startswith("//"):
        parsed = urlparse(f"https:{value}")
    elif "://" in value:
        parsed = urlparse(value)
    else:
        host_part = value.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
        if host_part.count(":") == 1:
            host, port = host_part.rsplit(":", 1)
            if port.isdigit():
                host_part = host
        return host_part

    if parsed.username or parsed.password:
        return ""
    return parsed.hostname or ""


def normalize_public_hostname(hostname: str) -> str:
    host = _host_from_input(hostname).strip().lower().rstrip(".")
    if not host or any(ch in host for ch in "@/\\: ?#"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid_hostname")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid_hostname")
    if not _HOSTNAME_RE.match(host) or host in _BLOCKED_HOSTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid_hostname")
    return host


def assert_public_https_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 443}
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid_webhook_url")
    if not parsed.hostname:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid_webhook_url")
    try:
        normalize_public_hostname(parsed.hostname)
    except HTTPException:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid_webhook_url") from None
    return url.strip()


def hostname_resolves_public(hostname: str) -> bool:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if _is_blocked_ip(ip):
            return False
    return True
