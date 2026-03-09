# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Redis-backed task queue for pipeline session runs.

Provides a lightweight FIFO queue using Redis lists (LPUSH/BRPOP),
per-user concurrency limiting, and task metadata tracking via Redis
hashes.  Built on the existing ``redis_client`` singleton.

Key patterns:
    taskq:pending                — FIFO list of session_ids
    taskq:meta:{session_id}     — hash with task metadata
    taskq:active:{user_id}      — set of active session_ids for a user
    taskq:active_count:{user_id}— integer counter of active sessions
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from backend.shared.redis_client import redis_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_CONCURRENT_PER_USER: int = 2
TASK_META_TTL: int = 86400  # 24 hours

# Redis key helpers
_PENDING_KEY = "taskq:pending"


def _meta_key(session_id: str) -> str:
    return f"taskq:meta:{session_id}"


def _active_set_key(user_id: str) -> str:
    return f"taskq:active:{user_id}"


def _active_count_key(user_id: str) -> str:
    return f"taskq:active_count:{user_id}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def enqueue_session(session_id: str, user_id: str) -> bool:
    """Add a session to the pending queue.

    Returns ``False`` without enqueuing if the user already has
    ``MAX_CONCURRENT_PER_USER`` active sessions.  Returns ``True`` on
    success.
    """
    r = redis_client.client

    # Check concurrency limit
    active_count = await get_user_active_count(user_id)
    if active_count >= MAX_CONCURRENT_PER_USER:
        logger.warning(
            "User %s at concurrency limit (%d/%d) — rejecting session %s",
            user_id,
            active_count,
            MAX_CONCURRENT_PER_USER,
            session_id,
        )
        return False

    # Store task metadata
    meta = {
        "session_id": session_id,
        "user_id": user_id,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    key = _meta_key(session_id)
    await r.hset(key, mapping=meta)
    await r.expire(key, TASK_META_TTL)

    # Push to the FIFO queue (LPUSH — consumers BRPOP from the right)
    await r.lpush(_PENDING_KEY, session_id)

    logger.info("Enqueued session %s for user %s", session_id, user_id)
    return True


async def dequeue_session() -> Optional[dict]:
    """Pop the next task from the pending queue.

    Uses BRPOP with a 1-second timeout so callers can loop without
    busy-waiting.  Returns the task metadata dict, or ``None`` if the
    queue is empty after the timeout.
    """
    r = redis_client.client

    result = await r.brpop(_PENDING_KEY, timeout=1)
    if result is None:
        return None

    # result is (key, value) — value is the session_id
    _, session_id = result

    meta_raw = await r.hgetall(_meta_key(session_id))
    if not meta_raw:
        logger.warning("Dequeued session %s but metadata missing", session_id)
        return None

    return dict(meta_raw)


async def mark_active(session_id: str) -> None:
    """Transition a task from *pending* to *active*.

    Updates the metadata hash, adds the session to the user's active
    set, and increments the user's active counter.
    """
    r = redis_client.client
    key = _meta_key(session_id)

    user_id = await r.hget(key, "user_id")
    if user_id is None:
        logger.error("mark_active: no metadata for session %s", session_id)
        return

    await r.hset(key, "status", "active")
    await r.expire(key, TASK_META_TTL)

    await r.sadd(_active_set_key(user_id), session_id)
    await r.incr(_active_count_key(user_id))

    logger.info("Session %s marked active (user %s)", session_id, user_id)


async def mark_complete(session_id: str) -> None:
    """Mark a task as completed and release the concurrency slot.

    Updates the metadata status, removes the session from the user's
    active set, and decrements the active counter (floored at 0).
    """
    r = redis_client.client
    key = _meta_key(session_id)

    user_id = await r.hget(key, "user_id")
    if user_id is None:
        logger.error("mark_complete: no metadata for session %s", session_id)
        return

    await r.hset(key, "status", "complete")
    await r.expire(key, TASK_META_TTL)

    await r.srem(_active_set_key(user_id), session_id)

    # Decrement, but never go below 0
    new_count = await r.decr(_active_count_key(user_id))
    if new_count < 0:
        await r.set(_active_count_key(user_id), 0)

    logger.info("Session %s marked complete (user %s)", session_id, user_id)


async def get_queue_position(session_id: str) -> int:
    """Return the position of a session in the queue.

    Returns 0 if the session is currently active (running).
    Returns 1+ indicating position in the pending queue (1 = next up).
    Returns -1 if the session is not found in either active or pending.
    """
    r = redis_client.client
    key = _meta_key(session_id)

    status = await r.hget(key, "status")
    if status == "active":
        return 0

    # Walk the pending list to find position.
    # LRANGE returns items in LPUSH order (newest first), but BRPOP
    # consumes from the right, so index 0 in LRANGE is the *last* to
    # be processed.  We reverse to get processing order.
    pending = await r.lrange(_PENDING_KEY, 0, -1)
    pending.reverse()  # now index 0 = next to be dequeued

    for idx, sid in enumerate(pending):
        if sid == session_id:
            return idx + 1  # 1-based position

    return -1


async def get_user_active_count(user_id: str) -> int:
    """Return the number of currently active sessions for a user."""
    r = redis_client.client
    count = await r.get(_active_count_key(user_id))
    return int(count) if count is not None else 0


async def flush_all_active() -> None:
    """Clear all active session counters and sets.

    Called on backend startup to prevent stale Redis state from blocking
    new sessions after a restart (in-memory session data is lost but
    Redis counters persist).
    """
    r = redis_client.client
    keys = []
    async for key in r.scan_iter("taskq:active:*"):
        keys.append(key)
    async for key in r.scan_iter("taskq:active_count:*"):
        keys.append(key)
    async for key in r.scan_iter("taskq:meta:*"):
        keys.append(key)
    # Also clear the pending queue
    keys.append(_PENDING_KEY)
    if keys:
        await r.delete(*keys)
        logger.info("Flushed %d stale task queue keys on startup", len(keys))
