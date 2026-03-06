"""Selector Memory -- learns which CSS selectors work for each job board.

Stores successful selectors in Postgres and retrieves the best ones for
future discovery runs. Selectors with higher success rates are ranked first.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

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
    last_checked TIMESTAMPTZ,
    last_check_passed BOOLEAN,
    UNIQUE (board, selector)
);
"""

_MIGRATE_COLUMNS = """\
ALTER TABLE board_selectors ADD COLUMN IF NOT EXISTS last_checked TIMESTAMPTZ;
ALTER TABLE board_selectors ADD COLUMN IF NOT EXISTS last_check_passed BOOLEAN;
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

_HEALTH_CHECK = """\
UPDATE board_selectors
SET last_checked = NOW(), last_check_passed = %(passed)s
WHERE board = %(board)s AND selector = %(selector)s;
"""

_GET_ALL_FOR_BOARD = """\
SELECT board, selector, success_count, fail_count, last_checked, last_check_passed
FROM board_selectors
WHERE board = %(board)s
ORDER BY (success_count - fail_count) DESC;
"""

_GET_ALL = """\
SELECT board, selector, success_count, fail_count, last_checked, last_check_passed
FROM board_selectors
ORDER BY board, (success_count - fail_count) DESC;
"""

# Default discovery selectors per board
_DEFAULTS: Dict[str, List[str]] = {
    "linkedin": [
        'div.base-card',
        'li.result-card',
        'div.job-search-card',
    ],
    "indeed": [
        'div.job_seen_beacon',
        'td.resultContent',
        'div.jobsearch-ResultsList > div',
    ],
    "glassdoor": [
        'li[data-test="jobListing"]',
        'li.JobsList_jobListItem__JBBUV',
    ],
    "ziprecruiter": [
        'article.job_result',
        'div.job_content',
    ],
}


def _connect() -> psycopg.Connection:
    """Create a sync connection (used infrequently, no pool needed)."""
    settings = get_settings()
    return psycopg.connect(settings.DATABASE_URL)


async def ensure_table() -> None:
    """Create the board_selectors table if it doesn't exist, and add new columns."""
    try:
        conn = _connect()
        try:
            conn.execute(_CREATE_TABLE)
            # Migrate: add health-check columns if missing (idempotent)
            for stmt in _MIGRATE_COLUMNS.strip().split("\n"):
                if stmt.strip():
                    conn.execute(stmt)
            conn.commit()
        finally:
            conn.close()
        logger.info("board_selectors table ensured (with health-check columns)")
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


def record_health_check(board: str, selector: str, passed: bool) -> None:
    """Update health-check timestamp and pass/fail for a discovery selector."""
    try:
        conn = _connect()
        try:
            conn.execute(_HEALTH_CHECK, {
                "board": board, "selector": selector, "passed": passed,
            })
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.debug("Failed to record health check", exc_info=True)


def get_all_for_board(board: str) -> List[Dict]:
    """Return all selectors for a board (for health-check iteration)."""
    try:
        conn = _connect()
        try:
            cur = conn.execute(_GET_ALL_FOR_BOARD, {"board": board})
            cols = ["board", "selector", "success_count", "fail_count",
                    "last_checked", "last_check_passed"]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            conn.close()
    except Exception:
        logger.debug("Failed to get selectors for %s", board, exc_info=True)
        return []


def get_all_selectors() -> List[Dict]:
    """Return all discovery selectors across all boards."""
    try:
        conn = _connect()
        try:
            cur = conn.execute(_GET_ALL)
            cols = ["board", "selector", "success_count", "fail_count",
                    "last_checked", "last_check_passed"]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            conn.close()
    except Exception:
        logger.debug("Failed to get all selectors", exc_info=True)
        return []


async def seed_defaults() -> None:
    """Insert default discovery selectors if they don't already exist."""
    try:
        conn = _connect()
        try:
            for board, selectors in _DEFAULTS.items():
                for selector in selectors:
                    conn.execute(_UPSERT, {"board": board, "selector": selector})
            conn.commit()
        finally:
            conn.close()
        logger.info("Seeded default discovery selectors")
    except Exception:
        logger.debug("Could not seed default discovery selectors", exc_info=True)
