# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Board credential management API routes.

Users can save/update/delete their job board login credentials.
Credentials are encrypted at rest and only decrypted when passed
to Skyvern during application.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.gateway.deps import get_current_user
from backend.shared.credential_store import (
    SUPPORTED_BOARDS,
    delete_credential,
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
