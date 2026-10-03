# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Browserbase settings and login-capture routes.

- GET/PUT /api/browserbase/settings: the user's API key (never echoed back),
  project id, proxy preference and per-board persisted-login Context ids.
- POST /api/browserbase/login-sessions: open a persisted-Context session for a
  board and return its Live View URL so the user can sign in by hand; the
  backend watches for the login cookie and stores the Context id.
- GET/DELETE /api/browserbase/login-sessions/{id}: poll or cancel a capture.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.browser import browserbase_client as bbc
from backend.browser import login_capture
from backend.gateway.deps import get_current_user
from backend.shared import browserbase_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/browserbase", tags=["browserbase"])


class BrowserbaseSettingsUpdate(BaseModel):
    api_key: Optional[str] = Field(
        default=None,
        description="New API key. Omit or null to keep the stored key; empty string clears it.",
    )
    project_id: Optional[str] = None
    proxies: bool = False
    context_ids: Dict[str, str] = Field(default_factory=dict)


def _hint(api_key: Optional[str]) -> Optional[str]:
    if not api_key:
        return None
    return f"…{api_key[-4:]}" if len(api_key) > 4 else "set"


def _public_settings(user_id: str) -> Dict[str, object]:
    saved = browserbase_store.get_browserbase_settings(user_id) or {}
    env = bbc.config_from_settings()
    effective = bbc.config_for_user(user_id)
    return {
        "api_key_set": bool(saved.get("api_key")),
        "api_key_hint": _hint(saved.get("api_key")),
        "project_id": saved.get("project_id") or "",
        "proxies": bool(saved.get("proxies", False)),
        "context_ids": saved.get("context_ids") or {},
        "boards": list(browserbase_store.CONTEXT_BOARDS),
        "login_capture_boards": sorted(login_capture.BOARD_LOGIN),
        "env_configured": env.configured,  # a server-wide key exists as a fallback
        "effective_configured": effective.configured,
    }


@router.get("/settings")
async def get_settings_route(request: Request):
    user = get_current_user(request)
    return _public_settings(user["id"])


@router.put("/settings")
async def update_settings_route(request: Request, body: BrowserbaseSettingsUpdate):
    user = get_current_user(request)
    unknown = sorted(k for k in body.context_ids if k.lower() not in browserbase_store.CONTEXT_BOARDS)
    if unknown:
        return JSONResponse(
            status_code=400,
            content={"detail": f"Unknown boards for context ids: {unknown}. "
                               f"Allowed: {list(browserbase_store.CONTEXT_BOARDS)}"},
        )
    browserbase_store.save_browserbase_settings(
        user["id"],
        api_key=body.api_key,
        keep_api_key=body.api_key is None,
        project_id=body.project_id,
        proxies=body.proxies,
        context_ids=body.context_ids,
    )
    logger.info("Browserbase settings saved for user %s", user["id"])
    return _public_settings(user["id"])


class LoginSessionStart(BaseModel):
    board: str


@router.post("/login-sessions", status_code=202)
async def start_login_session(request: Request, body: LoginSessionStart):
    """Open a persisted-Context session for *board* and return its Live View URL."""
    user = get_current_user(request)
    board = body.board.strip().lower()
    if board not in login_capture.BOARD_LOGIN:
        return JSONResponse(
            status_code=400,
            content={"detail": f"Login capture is not available for '{board}'. "
                               f"Supported: {sorted(login_capture.BOARD_LOGIN)}"},
        )
    config = bbc.config_for_user(user["id"])
    if not config.configured:
        return JSONResponse(
            status_code=400,
            content={"detail": "Save a Browserbase API key and project id first."},
        )
    try:
        capture = await login_capture.registry.start(
            user_id=user["id"], board=board, config=config,
            store_context=browserbase_store.set_context_id,
        )
    except bbc.BrowserbaseError as exc:
        logger.warning("Login capture start failed for user %s: %s", user["id"], exc)
        return JSONResponse(status_code=502, content={"detail": f"Browserbase error: {exc}"})
    return capture.public()


@router.get("/login-sessions/{capture_id}")
async def get_login_session(request: Request, capture_id: str):
    user = get_current_user(request)
    capture = login_capture.registry.get(capture_id, user["id"])
    if capture is None:
        return JSONResponse(status_code=404, content={"detail": "Unknown login session"})
    return capture.public()


@router.delete("/login-sessions/{capture_id}")
async def cancel_login_session(request: Request, capture_id: str):
    user = get_current_user(request)
    capture = await login_capture.registry.cancel(capture_id, user["id"])
    if capture is None:
        return JSONResponse(status_code=404, content={"detail": "Unknown login session"})
    return capture.public()
