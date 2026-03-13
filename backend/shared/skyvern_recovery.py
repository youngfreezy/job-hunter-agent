# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Recover orphaned Skyvern tasks after a deploy restart.

When the backend dies mid-Skyvern-poll, the task continues on Skyvern's side
but our backend never records the result. This module re-polls those orphaned
tasks on startup and writes the final results.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

import httpx

from backend.shared.config import get_settings

logger = logging.getLogger(__name__)

# Mirror constants from skyvern_applier.py
_TERMINAL_STATUSES = {"completed", "failed", "terminated", "canceled", "timed_out"}
_SUCCESS_STATUSES = {"completed"}
_POLL_INTERVAL_SECONDS = 5
_MAX_RECOVERY_POLL_SECONDS = 600  # 10 min max for recovery polls


def _get_orphaned_tasks() -> List[Dict[str, Any]]:
    """Find Skyvern tasks registered as 'running' — these were mid-poll when we died."""
    from backend.shared.db import get_pool

    pool = get_pool()
    with pool.connection() as conn:
        cur = conn.execute(
            """
            SELECT sta.session_id, sta.job_id, sta.task_id
            FROM skyvern_task_artifacts sta
            WHERE sta.skyvern_status = 'running'
            ORDER BY sta.created_at
            """
        )
        return [
            {"session_id": r[0], "job_id": r[1], "task_id": r[2]}
            for r in cur.fetchall()
        ]


def _finalize_pending_result(session_id: str, job_id: str, final_status: str, error_msg: str = "") -> None:
    """Update a pending application_result to its final status in-place.

    Uses UPDATE to preserve job_title, job_company, job_url, etc. that were
    written when the pending row was created.
    """
    from backend.shared.db import get_pool

    pool = get_pool()
    with pool.connection() as conn:
        cur = conn.execute(
            """
            UPDATE application_results
            SET status = %s, error_message = %s
            WHERE session_id = %s AND job_id = %s AND status = 'pending'
            """,
            (final_status, error_msg or None, session_id, job_id),
        )
        conn.commit()
        if cur.rowcount:
            logger.info("Recovery: updated pending result to %s (session=%s, job=%s)", final_status, session_id, job_id)
        else:
            logger.warning("Recovery: no pending result found to update (session=%s, job=%s)", session_id, job_id)


async def _poll_and_finalize(task: Dict[str, Any]) -> None:
    """Poll a single orphaned Skyvern task and write the final result."""
    settings = get_settings()
    base_url = settings.SKYVERN_API_URL.rstrip("/")
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if settings.SKYVERN_API_KEY:
        headers["x-api-key"] = settings.SKYVERN_API_KEY

    task_id = task["task_id"]
    session_id = task["session_id"]
    job_id = task["job_id"]

    logger.info("Recovery: polling orphaned Skyvern task %s (session=%s, job=%s)", task_id, session_id, job_id)

    elapsed = 0
    status = "running"
    result_data: Dict[str, Any] = {}

    async with httpx.AsyncClient(timeout=30) as client:
        while elapsed < _MAX_RECOVERY_POLL_SECONDS and status not in _TERMINAL_STATUSES:
            try:
                resp = await client.get(f"{base_url}/tasks/{task_id}", headers=headers)
                if resp.status_code == 200:
                    result_data = resp.json()
                    status = (result_data.get("status") or "unknown").lower()
                elif resp.status_code == 404:
                    logger.warning("Recovery: Skyvern task %s not found (404) — marking failed", task_id)
                    status = "failed"
                    break
                else:
                    logger.warning("Recovery: Skyvern poll returned %d for task %s", resp.status_code, task_id)
            except Exception as e:
                logger.warning("Recovery: poll error for task %s: %s", task_id, e)

            if status not in _TERMINAL_STATUSES:
                await asyncio.sleep(_POLL_INTERVAL_SECONDS)
                elapsed += _POLL_INTERVAL_SECONDS

    if status not in _TERMINAL_STATUSES:
        logger.warning("Recovery: task %s still running after %ds — giving up", task_id, elapsed)
        return

    failure_reason = result_data.get("failure_reason") or ""
    extracted = result_data.get("extracted_information") or {}

    # Update the artifact row with final status
    try:
        from backend.shared.screenshot_store import store_task_artifact

        await store_task_artifact(
            session_id=session_id,
            job_id=job_id,
            task_id=task_id,
            skyvern_status=status,
            failure_reason=failure_reason,
            extracted_information=extracted,
        )
    except Exception as e:
        logger.error("Recovery: failed to update artifact for task %s: %s", task_id, e)

    # Update the application_result from pending to final status (in-place UPDATE)
    is_success = status in _SUCCESS_STATUSES
    final_status = "submitted" if is_success else "failed"
    error_msg = failure_reason if not is_success else ""

    try:
        await asyncio.to_thread(_finalize_pending_result, session_id, job_id, final_status, error_msg)
        logger.info("Recovery: task %s finalized as %s (session=%s, job=%s)", task_id, final_status, session_id, job_id)
    except Exception as e:
        logger.error("Recovery: failed to update application_result for task %s: %s", task_id, e)


async def recover_orphaned_skyvern_tasks() -> int:
    """Find and re-poll all orphaned Skyvern tasks. Returns count recovered."""
    try:
        orphaned = await asyncio.to_thread(_get_orphaned_tasks)
    except Exception as e:
        logger.warning("Recovery: failed to query orphaned tasks: %s", e)
        return 0

    if not orphaned:
        return 0

    logger.info("Recovery: found %d orphaned Skyvern task(s) to re-poll", len(orphaned))

    recovered = 0
    for task in orphaned:
        try:
            await _poll_and_finalize(task)
            recovered += 1
        except Exception as e:
            logger.error("Recovery: failed to recover task %s: %s", task["task_id"], e)

    logger.info("Recovery: completed — %d/%d tasks recovered", recovered, len(orphaned))
    return recovered
