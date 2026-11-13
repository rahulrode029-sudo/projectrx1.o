"""URL safety checks.

Every URL the bot is asked to open passes through here first. The
important part is refusing addresses that point back at the machine
running the bot, which would otherwise let a message turn the bot
into a proxy for the local network.
"""

import ipaddress
import socket
from urllib.parse import urlparse

ALLOWED_SCHEMES = ("http", "https")

# Hosts that must never be fetched, whatever else is true of them.
BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata",
}

BLOCKED_DOMAIN_SUFFIXES = (
    ".local",
    ".internal",
    ".localhost",
)


class UrlVerdict:
    """The result of checking one URL."""

    def __init__(self, ok, reason="", url=""):
        self.ok = ok
        self.reason = reason
        self.url = url

    def __bool__(self):
        return self.ok

    def __repr__(self):
        return f"<UrlVerdict ok={self.ok} reason={self.reason!r}>"


def _is_private_address(host: str) -> bool:
    """True when the host resolves to a private or reserved address."""

    addresses = []

    try:
        for info in socket.getaddrinfo(host, None):
            addresses.append(info[4][0])
    except socket.gaierror:
        # If it does not resolve we cannot reach it either.
        return True

    for address in addresses:

        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return True

        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return True

    return False


def check_url(url: str) -> UrlVerdict:
    """Decide whether a URL is safe to fetch."""

    if not url or not url.strip():
        return UrlVerdict(False, "empty url")

    url = url.strip()

    try:
        parsed = urlparse(url)
    except ValueError as error:
        return UrlVerdict(False, f"could not parse url: {error}", url)

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        return UrlVerdict(False, f"scheme '{parsed.scheme}' is not allowed", url)

    host = (parsed.hostname or "").lower()

    if not host:
        return UrlVerdict(False, "no host in url", url)

    if host in BLOCKED_HOSTNAMES:
        return UrlVerdict(False, f"host '{host}' is blocked", url)

    for suffix in BLOCKED_DOMAIN_SUFFIXES:

        if host.endswith(suffix):
            return UrlVerdict(False, f"host '{host}' is blocked", url)

    if _is_private_address(host):
        return UrlVerdict(False, f"host '{host} is not a public address", url)

    return UrlVerdict(True, "", url)


def is_safe(url: str) -> bool:
    return bool(check_url(url))
