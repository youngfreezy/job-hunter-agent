# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Encrypted credential storage for job board logins.

Stores LinkedIn/Indeed/Glassdoor credentials per user, encrypted at rest
using Fernet (AES-128-CBC + HMAC) derived from NEXTAUTH_SECRET.
Credentials are passed to Skyvern's navigation_payload so the AI agent
can authenticate on boards that require login.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

from backend.shared.db import get_connection

logger = logging.getLogger(__name__)

# Supported boards that accept credentials
SUPPORTED_BOARDS = {"linkedin", "indeed", "glassdoor", "ziprecruiter"}

_fernet: Fernet | None = None

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS board_credentials (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    board TEXT NOT NULL,
    encrypted_credentials TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, board)
);
CREATE INDEX IF NOT EXISTS idx_board_creds_user ON board_credentials(user_id);
"""


def _get_fernet() -> Fernet:
    """Lazily initialise a Fernet instance keyed from NEXTAUTH_SECRET."""
    global _fernet
    if _fernet is not None:
        return _fernet

    from backend.shared.config import get_settings

    secret = get_settings().NEXTAUTH_SECRET
    if not secret:
        raise RuntimeError("NEXTAUTH_SECRET must be set for credential encryption")

    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"jobhunter-board-credentials",
        info=b"board-creds-at-rest",
    ).derive(secret.encode())

    _fernet = Fernet(base64.urlsafe_b64encode(derived))
    return _fernet


def _encrypt(data: dict) -> str:
    """Encrypt a dict to a Fernet token string."""
    return _get_fernet().encrypt(json.dumps(data).encode()).decode()


def _decrypt(token: str) -> dict:
    """Decrypt a Fernet token string back to a dict."""
    try:
        return json.loads(_get_fernet().decrypt(token.encode()))
    except InvalidToken:
        logger.error("Failed to decrypt board credentials — key may have changed")
        return {}


async def ensure_table() -> None:
    """Create the board_credentials table if it doesn't exist."""
    try:
        with get_connection() as conn:
            conn.execute(_CREATE_TABLE)
            conn.commit()
            logger.info("Board credentials table ensured")
    except Exception:
        logger.exception("Failed to create board_credentials table")


def save_credential(user_id: str, board: str, username: str, password: str) -> None:
    """Save (or update) encrypted credentials for a board."""
    if board not in SUPPORTED_BOARDS:
        raise ValueError(f"Unsupported board: {board}")

    encrypted = _encrypt({"username": username, "password": password})

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO board_credentials (user_id, board, encrypted_credentials, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (user_id, board)
            DO UPDATE SET encrypted_credentials = EXCLUDED.encrypted_credentials,
                         updated_at = NOW()
            """,
            (user_id, board, encrypted),
        )
        conn.commit()


def get_credentials(user_id: str) -> Dict[str, Dict[str, str]]:
    """Get all decrypted credentials for a user, keyed by board.

    Returns e.g. {"linkedin": {"username": "...", "password": "..."}}
    """
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT board, encrypted_credentials FROM board_credentials WHERE user_id = %s",
            (user_id,),
        )
        rows = cur.fetchall()

    result: Dict[str, Dict[str, str]] = {}
    for board, encrypted in rows:
        decrypted = _decrypt(encrypted)
        if decrypted:
            result[board] = decrypted
    return result


def get_credential(user_id: str, board: str) -> Optional[Dict[str, str]]:
    """Get decrypted credentials for a specific board."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT encrypted_credentials FROM board_credentials WHERE user_id = %s AND board = %s",
            (user_id, board),
        )
        row = cur.fetchone()

    if not row:
        return None
    return _decrypt(row[0]) or None


def delete_credential(user_id: str, board: str) -> bool:
    """Delete credentials for a specific board. Returns True if deleted."""
    with get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM board_credentials WHERE user_id = %s AND board = %s",
            (user_id, board),
        )
        conn.commit()
        return cur.rowcount > 0


def list_boards_with_credentials(user_id: str) -> List[str]:
    """Return list of board names that have saved credentials."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT board FROM board_credentials WHERE user_id = %s ORDER BY board",
            (user_id,),
        )
        return [row[0] for row in cur.fetchall()]
