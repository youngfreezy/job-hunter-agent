# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Waitlist signup endpoint — collects emails for launch notification."""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.shared.db import get_pool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/waitlist", tags=["waitlist"])

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS waitlist (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""

_table_ensured = False


def _ensure_table() -> None:
    global _table_ensured
    if _table_ensured:
        return
    try:
        pool = get_pool()
        with pool.connection() as conn:
            conn.execute(_TABLE_SQL)
            conn.commit()
        _table_ensured = True
    except Exception:
        logger.debug("Could not ensure waitlist table", exc_info=True)


class WaitlistRequest(BaseModel):
    email: str


@router.post("")
async def join_waitlist(body: WaitlistRequest):
    """Add email to the waitlist."""
    email = body.email.strip().lower()

    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Invalid email address")

    _ensure_table()

    try:
        pool = get_pool()
        with pool.connection() as conn:
            cur = conn.execute(
                "INSERT INTO waitlist (email) VALUES (%s) ON CONFLICT (email) DO NOTHING RETURNING id",
                (email,),
            )
            row = cur.fetchone()
            conn.commit()
    except Exception:
        logger.exception("Failed to insert waitlist email")
        raise HTTPException(status_code=500, detail="Server error")

    if row is None:
        raise HTTPException(status_code=409, detail="You're already on the waitlist!")

    logger.info("Waitlist signup: %s", email)
    return {"status": "ok", "message": "You're on the list!"}


@router.get("/count")
async def waitlist_count():
    """Return total waitlist signups (for admin dashboard)."""
    _ensure_table()
    try:
        pool = get_pool()
        with pool.connection() as conn:
            cur = conn.execute("SELECT count(*) FROM waitlist")
            count = cur.fetchone()[0]
        return {"count": count}
    except Exception:
        return {"count": 0}
