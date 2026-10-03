# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Thin Browserbase REST client.

Creates cloud browser sessions bound to persisted Contexts, fetches the live
view URL for a session, and releases sessions when done.  Uses httpx directly
so the backend does not take on the Browserbase SDK as a dependency.

Docs: https://docs.browserbase.com/reference/api
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from backend.shared.config import settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.browserbase.com/v1"


class BrowserbaseError(RuntimeError):
    """Raised when the Browserbase API returns an error."""


@dataclass
class BrowserbaseSession:
    id: str
    connect_url: str
    context_id: Optional[str]
    live_view_url: Optional[str] = None


def _headers() -> Dict[str, str]:
    key = settings.BROWSERBASE_API_KEY
    if not key:
        raise BrowserbaseError("BROWSERBASE_API_KEY is not set")
    return {"Content-Type": "application/json", "X-BB-API-Key": key}


def context_id_for_board(board: Optional[str]) -> Optional[str]:
    """Resolve a persisted Context id for a job board from settings.

    ``BROWSERBASE_CONTEXT_IDS`` is a comma-separated ``board=context_id`` list,
    for example ``indeed=f142b56c-...,linkedin=9a1c...,default=...``.  The
    ``default`` entry is used when no board-specific id exists.
    """
    raw = settings.BROWSERBASE_CONTEXT_IDS or ""
    mapping: Dict[str, str] = {}
    for part in raw.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            mapping[k.strip().lower()] = v.strip()
    key = (board or "").lower()
    if hasattr(board, "value"):
        key = str(getattr(board, "value")).lower()
    return mapping.get(key) or mapping.get("default")


async def create_context(name: str) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{API_BASE}/contexts",
            headers=_headers(),
            json={"projectId": settings.BROWSERBASE_PROJECT_ID, "name": name},
        )
    if r.status_code >= 400:
        raise BrowserbaseError(f"create_context failed: {r.status_code} {r.text[:200]}")
    return r.json()["id"]


async def create_session(
    *,
    context_id: Optional[str] = None,
    persist: bool = True,
    proxies: Optional[bool] = None,
    timeout: Optional[int] = None,
    viewport: Optional[Dict[str, int]] = None,
) -> BrowserbaseSession:
    """Create a Browserbase session and return its CDP connect URL.

    When *context_id* is given the session loads that Context's cookies and
    storage and, with *persist*, writes them back on close.
    """
    if not settings.BROWSERBASE_PROJECT_ID:
        raise BrowserbaseError("BROWSERBASE_PROJECT_ID is not set")

    browser_settings: Dict[str, Any] = {}
    if context_id:
        browser_settings["context"] = {"id": context_id, "persist": persist}
    if viewport:
        browser_settings["viewport"] = viewport

    body: Dict[str, Any] = {"projectId": settings.BROWSERBASE_PROJECT_ID}
    if browser_settings:
        body["browserSettings"] = browser_settings
    use_proxies = settings.BROWSERBASE_PROXIES if proxies is None else proxies
    if use_proxies:
        body["proxies"] = True
    body["timeout"] = timeout or settings.BROWSERBASE_SESSION_TIMEOUT

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{API_BASE}/sessions", headers=_headers(), json=body)
        if r.status_code >= 400:
            raise BrowserbaseError(f"create_session failed: {r.status_code} {r.text[:300]}")
        data = r.json()
        live_view: Optional[str] = None
        try:
            dbg = await client.get(f"{API_BASE}/sessions/{data['id']}/debug", headers=_headers())
            if dbg.status_code < 400:
                live_view = dbg.json().get("debuggerFullscreenUrl") or dbg.json().get("debuggerUrl")
        except httpx.HTTPError:
            logger.debug("Could not fetch Browserbase live view URL", exc_info=True)

    logger.info(
        "Browserbase session %s created (context=%s, proxies=%s, timeout=%ss)",
        data["id"], context_id or "none", use_proxies, body["timeout"],
    )
    return BrowserbaseSession(
        id=data["id"],
        connect_url=data["connectUrl"],
        context_id=context_id,
        live_view_url=live_view,
    )


async def release_session(session_id: str) -> None:
    """Ask Browserbase to end a session (idempotent; errors are logged, not raised)."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{API_BASE}/sessions/{session_id}",
                headers=_headers(),
                json={"projectId": settings.BROWSERBASE_PROJECT_ID, "status": "REQUEST_RELEASE"},
            )
        if r.status_code >= 400:
            logger.warning("release_session %s: %s %s", session_id, r.status_code, r.text[:200])
    except (httpx.HTTPError, BrowserbaseError):
        logger.warning("release_session %s failed", session_id, exc_info=True)


async def get_session(session_id: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{API_BASE}/sessions/{session_id}", headers=_headers())
    if r.status_code >= 400:
        raise BrowserbaseError(f"get_session failed: {r.status_code} {r.text[:200]}")
    return r.json()
