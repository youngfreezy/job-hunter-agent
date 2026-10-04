"""Validate webhook destinations before storage and every outbound attempt."""
import ipaddress
import socket
from urllib.parse import urlsplit

import httpx


def resolve_webhook_destination(url: str) -> tuple[httpx.URL, str, str]:
    """Resolve once and pin transport IP, retaining original HTTP Host and TLS SNI."""
    message = 'Webhook URL must use HTTPS and resolve only to public internet addresses.'
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.fragment or '\\' in url
                or any(c.isspace() or ord(c) < 32 for c in url)):
            raise ValueError(message)
        records = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        if not records or any(not ipaddress.ip_address(record[4][0].split('%')[0]).is_global for record in records):
            raise ValueError(message)
    except (ValueError, OSError) as exc:
        raise ValueError(message) from exc

    original = httpx.URL(url)
    hostname = original.raw_host.decode("ascii")
    authority = original.netloc.decode("ascii")
    return original.copy_with(host=records[0][4][0]), authority, hostname


def validate_webhook_url(url: str) -> None:
    resolve_webhook_destination(url)
