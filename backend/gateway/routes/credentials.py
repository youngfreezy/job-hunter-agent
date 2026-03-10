# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Board credential management API routes.

Users can save/update/delete their job board login credentials.
Credentials are encrypted at rest and only decrypted when passed
to Skyvern during application.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.gateway.deps import get_current_user
from backend.shared.config import get_settings
from backend.shared.credential_store import (
    SUPPORTED_BOARDS,
    delete_credential,
    get_credential,
    list_boards_with_credentials,
    save_credential,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/credentials", tags=["credentials"])


class SaveCredentialRequest(BaseModel):
    board: str
    username: str
    password: str


class BoardCredentialStatus(BaseModel):
    board: str
    has_credentials: bool


@router.get("")
async def get_credential_status(user=Depends(get_current_user)) -> List[BoardCredentialStatus]:
    """List all supported boards and whether the user has saved credentials."""
    saved = set(list_boards_with_credentials(user["id"]))
    return [
        BoardCredentialStatus(board=board, has_credentials=board in saved)
        for board in sorted(SUPPORTED_BOARDS)
    ]


@router.put("")
async def save_board_credential(
    req: SaveCredentialRequest,
    user=Depends(get_current_user),
) -> JSONResponse:
    """Save or update credentials for a job board."""
    if req.board not in SUPPORTED_BOARDS:
        return JSONResponse(
            status_code=400,
            content={"detail": f"Unsupported board: {req.board}. Supported: {sorted(SUPPORTED_BOARDS)}"},
        )

    save_credential(user["id"], req.board, req.username, req.password)
    logger.info("Saved %s credentials for user %s", req.board, user["id"])
    return JSONResponse(content={"status": "saved", "board": req.board})


@router.delete("/{board}")
async def delete_board_credential(
    board: str,
    user=Depends(get_current_user),
) -> JSONResponse:
    """Delete saved credentials for a job board."""
    deleted = delete_credential(user["id"], board)
    if not deleted:
        return JSONResponse(status_code=404, content={"detail": "No credentials found for this board"})
    logger.info("Deleted %s credentials for user %s", board, user["id"])
    return JSONResponse(content={"status": "deleted", "board": board})


# ---------------------------------------------------------------------------
# Credential validation via Skyvern
# ---------------------------------------------------------------------------

BOARD_LOGIN_URLS: Dict[str, str] = {
    "linkedin": "https://www.linkedin.com/login",
    "indeed": "https://secure.indeed.com/account/login",
    "glassdoor": "https://www.glassdoor.com/profile/login_input.htm",
    "ziprecruiter": "https://www.ziprecruiter.com/login",
}

_SKYVERN_TERMINAL = {"completed", "failed", "terminated", "canceled", "timed_out"}
_SKYVERN_POLL_INTERVAL = 5


class ValidateCredentialRequest(BaseModel):
    board: str


@router.post("/validate")
async def validate_board_credential(
    req: ValidateCredentialRequest,
    user=Depends(get_current_user),
) -> JSONResponse:
    """Validate saved credentials by attempting a Skyvern login-only task."""
    settings = get_settings()

    if not settings.SKYVERN_ENABLED:
        return JSONResponse(
            status_code=503,
            content={"detail": "Credential validation unavailable (Skyvern not enabled)"},
        )

    if req.board not in BOARD_LOGIN_URLS:
        return JSONResponse(
            status_code=400,
            content={"detail": f"Validation not supported for board: {req.board}"},
        )

    cred = get_credential(user["id"], req.board)
    if not cred:
        return JSONResponse(
            status_code=404,
            content={"detail": "No credentials saved for this board"},
        )

    base_url = settings.SKYVERN_API_URL.rstrip("/")
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if settings.SKYVERN_API_KEY:
        headers["x-api-key"] = settings.SKYVERN_API_KEY

    board_label = req.board.title()
    task_body = {
        "url": BOARD_LOGIN_URLS[req.board],
        "navigation_goal": (
            f"Log in to {board_label} using the provided username and password. "
            "After submitting the login form, check if the login was successful. "
            "If you see a dashboard, feed, or profile page, the login succeeded. "
            "If you see an error message like 'incorrect password' or a CAPTCHA, "
            "the login failed. Do NOT navigate anywhere else after login."
        ),
        "data_extraction_goal": (
            "Determine if the login was successful. Extract: "
            "login_success (boolean), error_message (string if login failed)."
        ),
        "navigation_payload": {
            "username": cred["username"],
            "password": cred["password"],
        },
        "extracted_information_schema": {
            "type": "object",
            "properties": {
                "login_success": {"type": "boolean"},
                "error_message": {"type": "string"},
            },
        },
        "proxy_location": "RESIDENTIAL",
    }

    logger.info("Validating %s credentials for user %s via Skyvern", req.board, user["id"])

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{base_url}/tasks", json=task_body, headers=headers)
            resp.raise_for_status()
            task_data = resp.json()

            task_id = task_data.get("task_id") or task_data.get("id") or task_data.get("run_id")
            if not task_id:
                return JSONResponse(
                    status_code=502,
                    content={"detail": "Skyvern returned no task ID"},
                )

            # Poll for completion (max 90s for login-only task)
            elapsed = 0
            max_wait = 90
            status = "created"
            result_data: Dict[str, Any] = {}

            while elapsed < max_wait and status not in _SKYVERN_TERMINAL:
                await asyncio.sleep(_SKYVERN_POLL_INTERVAL)
                elapsed += _SKYVERN_POLL_INTERVAL
                try:
                    poll_resp = await client.get(f"{base_url}/tasks/{task_id}", headers=headers)
                    poll_resp.raise_for_status()
                    result_data = poll_resp.json()
                    status = (result_data.get("status") or "unknown").lower()
                except Exception:
                    continue

            if status not in _SKYVERN_TERMINAL:
                return JSONResponse(content={
                    "valid": False,
                    "error": "Verification timed out. Try again later.",
                })

            extracted = result_data.get("extracted_information") or {}
            login_success = extracted.get("login_success", False)
            error_msg = extracted.get("error_message", "")

            if status == "completed" and login_success:
                logger.info("Credential validation succeeded for %s (user %s)", req.board, user["id"])
                return JSONResponse(content={"valid": True})
            else:
                reason = error_msg or result_data.get("failure_reason") or "Login failed"
                logger.info("Credential validation failed for %s: %s", req.board, reason)
                return JSONResponse(content={"valid": False, "error": str(reason)[:200]})

    except httpx.HTTPStatusError as e:
        logger.error("Skyvern API error during validation: %s", e.response.text[:300])
        return JSONResponse(
            status_code=502,
            content={"detail": f"Skyvern API error: {e.response.status_code}"},
        )
    except httpx.RequestError as e:
        logger.error("Skyvern connection error during validation: %s", e)
        return JSONResponse(
            status_code=502,
            content={"detail": "Could not connect to Skyvern service"},
        )
