# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Thin Browserbase REST client.

Creates cloud browser sessions bound to persisted Contexts, fetches the live
view URL for a session, and releases sessions when done.  Uses httpx directly
so the backend does not take on the Browserbase SDK as a dependency.

Every call takes an optional :class:`BrowserbaseConfig`.  Without one the
process-wide settings (``BROWSERBASE_*`` env vars) are used; the Settings UI
stores per-user overrides which :func:`config_for_user` layers on top.

Docs: https://docs.browserbase.com/reference/api
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
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


@dataclass
class BrowserbaseConfig:
    """Resolved Browserbase credentials and options for one caller."""

    api_key: Optional[str] = None
    project_id: Optional[str] = None
    proxies: bool = False
    session_timeout: int = 900
    context_ids: Dict[str, str] = field(default_factory=dict)  # board -> Context id
    source: str = "env"  # "env" or "user:<id>", for logs only

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.project_id)


def _parse_context_ids(raw: Optional[str]) -> Dict[str, str]:
    """Parse ``board=ctx,board=ctx`` into a dict (keys lower-cased)."""
    mapping: Dict[str, str] = {}
    for part in (raw or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip() and v.strip():
                mapping[k.strip().lower()] = v.strip()
    return mapping


def config_from_settings() -> BrowserbaseConfig:
    """The process-wide configuration from ``BROWSERBASE_*`` settings."""
    return BrowserbaseConfig(
        api_key=settings.BROWSERBASE_API_KEY or None,
        project_id=settings.BROWSERBASE_PROJECT_ID or None,
        proxies=bool(settings.BROWSERBASE_PROXIES),
        session_timeout=int(settings.BROWSERBASE_SESSION_TIMEOUT),
        context_ids=_parse_context_ids(settings.BROWSERBASE_CONTEXT_IDS),
        source="env",
    )


def config_for_user(user_id: Optional[str]) -> BrowserbaseConfig:
    """Env configuration with the user's saved Browserbase settings layered on.

    A user override replaces the env value only when it is set; per-board
    Context ids merge only for the configured owner. Other accounts and anonymous
    callers never inherit server login contexts.
    """
    base = config_from_settings()
    if not user_id or user_id != settings.BROWSERBASE_CONTEXT_USER_ID:
        base.context_ids = {}
    if not user_id or user_id == "unknown":
        return base
    from backend.shared.browserbase_store import get_browserbase_settings

    saved = get_browserbase_settings(user_id)
    if not saved:
        return base
    merged_contexts = dict(base.context_ids)
    merged_contexts.update({k.lower(): v for k, v in (saved.get("context_ids") or {}).items() if v})
    return BrowserbaseConfig(
        api_key=saved.get("api_key") or base.api_key,
        project_id=saved.get("project_id") or base.project_id,
        proxies=bool(saved["proxies"]) if saved.get("proxies") is not None else base.proxies,
        session_timeout=base.session_timeout,
        context_ids=merged_contexts,
        source=f"user:{user_id}",
    )


def _resolve(config: Optional[BrowserbaseConfig]) -> BrowserbaseConfig:
    return config if config is not None else config_from_settings()


def _headers(config: Optional[BrowserbaseConfig] = None) -> Dict[str, str]:
    cfg = _resolve(config)
    if not cfg.api_key:
        raise BrowserbaseError("BROWSERBASE_API_KEY is not set")
    return {"Content-Type": "application/json", "X-BB-API-Key": cfg.api_key}


def context_id_for_board(board: Optional[str], config: Optional[BrowserbaseConfig] = None) -> Optional[str]:
    """Resolve a persisted Context id for a job board.

    The mapping comes from ``BROWSERBASE_CONTEXT_IDS`` (``board=context_id``
    pairs, for example ``indeed=f142b56c-...,default=...``) merged with the
    user's saved per-board ids.  ``default`` is used when no board-specific
    id exists.
    """
    mapping = _resolve(config).context_ids
    key = (board or "").lower()
    if hasattr(board, "value"):
        key = str(getattr(board, "value")).lower()
    return mapping.get(key) or mapping.get("default")


async def create_context(name: str, config: Optional[BrowserbaseConfig] = None) -> str:
    cfg = _resolve(config)
    if not cfg.project_id:
        raise BrowserbaseError("BROWSERBASE_PROJECT_ID is not set")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{API_BASE}/contexts",
            headers=_headers(cfg),
            json={"projectId": cfg.project_id, "name": name},
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
    config: Optional[BrowserbaseConfig] = None,
) -> BrowserbaseSession:
    """Create a Browserbase session and return its CDP connect URL.

    When *context_id* is given the session loads that Context's cookies and
    storage and, with *persist*, writes them back on close.
    """
    cfg = _resolve(config)
    if not cfg.project_id:
        raise BrowserbaseError("BROWSERBASE_PROJECT_ID is not set")

    browser_settings: Dict[str, Any] = {"solveCaptchas": True}
    if context_id:
        browser_settings["context"] = {"id": context_id, "persist": persist}
    if viewport:
        browser_settings["viewport"] = viewport

    body: Dict[str, Any] = {"projectId": cfg.project_id}
    if browser_settings:
        body["browserSettings"] = browser_settings
    use_proxies = cfg.proxies if proxies is None else proxies
    if use_proxies:
        body["proxies"] = True
    body["timeout"] = timeout or cfg.session_timeout

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{API_BASE}/sessions", headers=_headers(cfg), json=body)
        if r.status_code >= 400:
            raise BrowserbaseError(f"create_session failed: {r.status_code} {r.text[:300]}")
        data = r.json()
        live_view: Optional[str] = None
        try:
            dbg = await client.get(f"{API_BASE}/sessions/{data['id']}/debug", headers=_headers(cfg))
            if dbg.status_code < 400:
                live_view = dbg.json().get("debuggerFullscreenUrl") or dbg.json().get("debuggerUrl")
        except httpx.HTTPError:
            logger.debug("Could not fetch Browserbase live view URL", exc_info=True)

    logger.info(
        "Browserbase session %s created (context=%s, proxies=%s, timeout=%ss, config=%s)",
        data["id"], context_id or "none", use_proxies, body["timeout"], cfg.source,
    )
    return BrowserbaseSession(
        id=data["id"],
        connect_url=data["connectUrl"],
        context_id=context_id,
        live_view_url=live_view,
    )


async def release_session(session_id: str, config: Optional[BrowserbaseConfig] = None) -> None:
    """Ask Browserbase to end a session (idempotent; errors are logged, not raised)."""
    cfg = _resolve(config)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{API_BASE}/sessions/{session_id}",
                headers=_headers(cfg),
                json={"projectId": cfg.project_id, "status": "REQUEST_RELEASE"},
            )
        if r.status_code >= 400:
            logger.warning("release_session %s: %s %s", session_id, r.status_code, r.text[:200])
    except (httpx.HTTPError, BrowserbaseError):
        logger.warning("release_session %s failed", session_id, exc_info=True)


async def get_session(session_id: str, config: Optional[BrowserbaseConfig] = None) -> Dict[str, Any]:
    cfg = _resolve(config)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{API_BASE}/sessions/{session_id}", headers=_headers(cfg))
    if r.status_code >= 400:
        raise BrowserbaseError(f"get_session failed: {r.status_code} {r.text[:200]}")
    return r.json()
