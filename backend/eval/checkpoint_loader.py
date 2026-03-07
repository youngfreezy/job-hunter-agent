"""Load session state from LangGraph Postgres checkpoints."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.shared.config import get_settings

logger = logging.getLogger(__name__)


async def _get_pool():
    """Create a temporary connection pool for eval (not tied to the running app)."""
    from psycopg_pool import AsyncConnectionPool

    settings = get_settings()
    pool = AsyncConnectionPool(
        conninfo=settings.DATABASE_URL,
        min_size=1,
        max_size=3,
        open=False,
    )
    await pool.open()
    return pool


async def load_session_state(session_id: str) -> Optional[Dict[str, Any]]:
    """Load channel_values from the latest checkpoint for a session.

    Returns the full state dict (JobHunterState fields) or None if not found.
    """
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    pool = await _get_pool()
    try:
        checkpointer = AsyncPostgresSaver(pool)
        config = {"configurable": {"thread_id": session_id}}
        state = await checkpointer.aget(config)

        if state is None:
            return None

        cp = state
        if hasattr(state, "checkpoint"):
            cp = state.checkpoint
        cv = cp.get("channel_values", cp) if isinstance(cp, dict) else cp
        return cv if isinstance(cv, dict) else None
    finally:
        await pool.close()


async def list_session_ids() -> List[str]:
    """Return all distinct session (thread) IDs from the checkpoints table."""
    pool = await _get_pool()
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT DISTINCT thread_id FROM checkpoints WHERE checkpoint_ns = ''"
                )
                rows = await cur.fetchall()
                return [row[0] for row in rows]
    finally:
        await pool.close()


async def ensure_eval_table() -> None:
    """Create the eval_runs table if it doesn't exist."""
    pool = await _get_pool()
    try:
        async with pool.connection() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS eval_runs (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    session_id TEXT NOT NULL,
                    eval_timestamp TIMESTAMPTZ DEFAULT NOW(),
                    overall_score FLOAT,
                    metrics JSONB,
                    metadata JSONB
                )
            """)
    finally:
        await pool.close()


async def store_eval_result(result: dict) -> None:
    """Store an eval result in the eval_runs table."""
    import json

    pool = await _get_pool()
    try:
        async with pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO eval_runs (session_id, overall_score, metrics, metadata)
                VALUES (%s, %s, %s::jsonb, %s::jsonb)
                """,
                (
                    result["session_id"],
                    result["overall_score"],
                    json.dumps([m.dict() if hasattr(m, "dict") else m for m in result.get("metrics", [])]),
                    json.dumps(result.get("metadata", {})),
                ),
            )
    finally:
        await pool.close()
