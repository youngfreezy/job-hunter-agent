# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Session outcome storage for self-improvement feedback loop.

Records structured metrics at the end of each session so EvoAgentX
can use historical outcomes to optimize prompts via TextGrad.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from backend.shared.db import get_pool

logger = logging.getLogger(__name__)

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS session_outcomes (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    discovery_count INT DEFAULT 0,
    scored_count INT DEFAULT 0,
    submitted_count INT DEFAULT 0,
    failed_count INT DEFAULT 0,
    skipped_count INT DEFAULT 0,
    success_rate FLOAT DEFAULT 0.0,
    avg_fit_score FLOAT DEFAULT 0.0,
    error_categories JSONB,
    ats_breakdown JSONB,
    prompts_used JSONB,
    search_config JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""

_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_session_outcomes_created
    ON session_outcomes (created_at DESC);
"""

_ensured = False


def _ensure_table() -> None:
    global _ensured
    if _ensured:
        return
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(_TABLE_SQL)
        conn.execute(_INDEX_SQL)
        conn.commit()
    _ensured = True


def record_outcome(session_id: str, metrics: Dict[str, Any]) -> None:
    """Record session outcome metrics for the feedback loop."""
    _ensure_table()

    submitted = metrics.get("submitted_count", 0)
    failed = metrics.get("failed_count", 0)
    total_attempted = submitted + failed
    success_rate = submitted / total_attempted if total_attempted > 0 else 0.0

    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO session_outcomes (
                session_id, discovery_count, scored_count,
                submitted_count, failed_count, skipped_count,
                success_rate, avg_fit_score,
                error_categories, ats_breakdown, prompts_used, search_config
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session_id,
                metrics.get("discovery_count", 0),
                metrics.get("scored_count", 0),
                submitted,
                failed,
                metrics.get("skipped_count", 0),
                success_rate,
                metrics.get("avg_fit_score", 0.0),
                json.dumps(metrics.get("error_categories", {})),
                json.dumps(metrics.get("ats_breakdown", {})),
                json.dumps(metrics.get("prompts_used", {})),
                json.dumps(metrics.get("search_config", {})),
            ),
        )
        conn.commit()

    logger.info(
        "Recorded outcome for session %s: %d submitted, %d failed (%.0f%% success)",
        session_id, submitted, failed, success_rate * 100,
    )


def get_outcomes_for_optimization(min_sessions: int = 10) -> List[Dict[str, Any]]:
    """Return recent session outcomes for TextGrad optimization.

    Returns empty list if fewer than min_sessions are available.
    """
    _ensure_table()
    pool = get_pool()
    with pool.connection() as conn:
        count_row = conn.execute("SELECT COUNT(*) FROM session_outcomes").fetchone()
        if count_row[0] < min_sessions:
            return []

        rows = conn.execute(
            """SELECT session_id, discovery_count, scored_count,
                      submitted_count, failed_count, skipped_count,
                      success_rate, avg_fit_score,
                      error_categories, ats_breakdown, prompts_used, search_config,
                      created_at
               FROM session_outcomes
               ORDER BY created_at DESC
               LIMIT 100"""
        ).fetchall()

    return [
        {
            "session_id": r[0],
            "discovery_count": r[1],
            "scored_count": r[2],
            "submitted_count": r[3],
            "failed_count": r[4],
            "skipped_count": r[5],
            "success_rate": r[6],
            "avg_fit_score": r[7],
            "error_categories": r[8] if isinstance(r[8], dict) else json.loads(r[8] or "{}"),
            "ats_breakdown": r[9] if isinstance(r[9], dict) else json.loads(r[9] or "{}"),
            "prompts_used": r[10] if isinstance(r[10], dict) else json.loads(r[10] or "{}"),
            "search_config": r[11] if isinstance(r[11], dict) else json.loads(r[11] or "{}"),
            "created_at": r[12].isoformat() if r[12] else None,
        }
        for r in rows
    ]


def get_outcome_count() -> int:
    """Return total number of recorded outcomes."""
    _ensure_table()
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM session_outcomes").fetchone()
    return row[0]
