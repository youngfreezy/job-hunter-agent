"""Selector Memory -- learns which CSS selectors work for each job board.

Stores successful selectors in Postgres and retrieves the best ones for
future discovery runs. Selectors with higher success rates are ranked first.
"""

from __future__ import annotations

import logging
from typing import List, Optional

import psycopg

from backend.shared.config import get_settings

logger = logging.getLogger(__name__)

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS board_selectors (
    id SERIAL PRIMARY KEY,
    board TEXT NOT NULL,
    selector TEXT NOT NULL,
    success_count INT NOT NULL DEFAULT 1,
    fail_count INT NOT NULL DEFAULT 0,
    last_used TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (board, selector)
);
"""

_UPSERT = """\
INSERT INTO board_selectors (board, selector, success_count, last_used)
VALUES (%(board)s, %(selector)s, 1, NOW())
ON CONFLICT (board, selector)
DO UPDATE SET
    success_count = board_selectors.success_count + 1,
    last_used = NOW();
"""

_INCREMENT_FAIL = """\
UPDATE board_selectors
SET fail_count = fail_count + 1, last_used = NOW()
WHERE board = %(board)s AND selector = %(selector)s;
"""

_GET_TOP = """\
SELECT selector, success_count, fail_count
FROM board_selectors
WHERE board = %(board)s
ORDER BY (success_count - fail_count) DESC, last_used DESC
LIMIT %(limit)s;
"""


def _connect() -> psycopg.Connection:
    """Create a sync connection (used infrequently, no pool needed)."""
    settings = get_settings()
    return psycopg.connect(settings.DATABASE_URL)


async def ensure_table() -> None:
    """Create the board_selectors table if it doesn't exist."""
    try:
        conn = _connect()
        try:
            conn.execute(_CREATE_TABLE)
            conn.commit()
        finally:
            conn.close()
        logger.info("board_selectors table ensured")
    except Exception:
        logger.debug("Could not create board_selectors table", exc_info=True)


def record_success(board: str, selector: str) -> None:
    """Record a successful selector extraction for a board."""
    try:
        conn = _connect()
        try:
            conn.execute(_UPSERT, {"board": board, "selector": selector})
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.debug("Failed to record selector success", exc_info=True)


def record_failure(board: str, selector: str) -> None:
    """Record a failed selector attempt for a board."""
    try:
        conn = _connect()
        try:
            conn.execute(_INCREMENT_FAIL, {"board": board, "selector": selector})
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.debug("Failed to record selector failure", exc_info=True)


def get_top_selectors(board: str, limit: int = 5) -> List[str]:
    """Get the top-performing selectors for a board, ranked by net success."""
    try:
        conn = _connect()
        try:
            cur = conn.execute(_GET_TOP, {"board": board, "limit": limit})
            rows = cur.fetchall()
            return [row[0] for row in rows]
        finally:
            conn.close()
    except Exception:
        logger.debug("Failed to get selectors for %s", board, exc_info=True)
        return []
