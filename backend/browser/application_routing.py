"""Application destinations and ordering; discovery provenance stays on Indeed."""
from __future__ import annotations

import ipaddress
import asyncio
import re
import socket
from urllib.parse import urlsplit


def is_public_application_url(url: str) -> bool:
    """Permit only ordinary HTTPS destinations, never credentials or local services."""
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or '').lower().rstrip('.')
        if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return ('.' in host and bool(re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)+', host))
                    and not host.endswith(('.local', '.localhost', '.internal', '.invalid', '.test'))
                    and not host.replace('.', '').isdigit())
    except ValueError:
        return False


async def resolves_publicly(url: str) -> bool:
    """Reject hostnames resolving to private or metadata-service addresses."""
    if not is_public_application_url(url):
        return False
    try:
        addresses = await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(
            urlsplit(url).hostname, 443, type=socket.SOCK_STREAM,
        ), timeout=5)
        return bool(addresses) and all(ipaddress.ip_address(item[4][0]).is_global for item in addresses)
    except (OSError, TimeoutError, ValueError):
        return False


def ordered_pending_jobs(queue: list[str], done: set[str], routes: dict) -> list[str]:
    """Finish Indeed forms first, then drain the employer-site queue once per job."""
    pending = list(dict.fromkeys(job_id for job_id in queue if job_id not in done))
    return [job_id for job_id in pending if job_id not in routes] + [
        job_id for job_id in pending if job_id in routes
    ]
