# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Redis-backed task queue for pipeline session runs.

Provides a lightweight FIFO queue using Redis lists (LPUSH/BRPOP),
atomic per-user admission limiting, and task metadata tracking via Redis
hashes.  Built on the existing ``redis_client`` singleton.

Key patterns:
    taskq:pending                — FIFO list of session_ids
    taskq:meta:{session_id}     — hash with task metadata
    taskq:active:{user_id}      — set of active session_ids for a user
    taskq:active_count:{user_id}— compatibility counter of admitted sessions
    taskq:reserved:{user_id}    — sorted set of admitted sessions and fixed expiries
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from backend.shared.redis_client import redis_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_CONCURRENT_PER_USER: int = 5
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


class QueueUnavailable(RuntimeError):
    """Admission is unconfirmed; paid work must not start."""


class QueueAtCapacity(RuntimeError):
    """No execution slot is available for this owner."""


def _reservations_key(user_id: str) -> str:
    return f"taskq:reserved:{user_id}"


# Each member has its own fixed expiry. Repeated admission/activation does not
# extend a crashed worker's lease. Import legacy active members using their
# existing metadata TTL, so rolling deployment does not forget old reservations.
_RECONCILE = """
local now = tonumber(redis.call('TIME')[1])
local expired = redis.call('ZRANGEBYSCORE', KEYS[5], '-inf', now)
for _, sid in ipairs(expired) do
    redis.call('SREM', KEYS[3], sid)
    redis.call('LREM', KEYS[2], 0, sid)
end
redis.call('ZREMRANGEBYSCORE', KEYS[5], '-inf', now)
for _, sid in ipairs(redis.call('SMEMBERS', KEYS[3])) do
    if not redis.call('ZSCORE', KEYS[5], sid) then
        local ttl = redis.call('TTL', ARGV[5] .. sid)
        if ttl > 0 then
            redis.call('ZADD', KEYS[5], now + ttl, sid)
        else
            redis.call('SREM', KEYS[3], sid)
        end
    end
end
"""

_ADMIT = _RECONCILE + """
local owner = redis.call('HGET', KEYS[1], 'user_id')
local status = redis.call('HGET', KEYS[1], 'status')
if owner and owner ~= ARGV[2] then return 0 end
if redis.call('ZSCORE', KEYS[5], ARGV[1]) then return 1 end
if redis.call('ZCARD', KEYS[5]) >= tonumber(ARGV[3]) then return 0 end
redis.call('HSET', KEYS[1], 'session_id', ARGV[1], 'user_id', ARGV[2],
           'status', 'pending', 'created_at', ARGV[6])
redis.call('EXPIRE', KEYS[1], ARGV[4])
redis.call('ZADD', KEYS[5], now + tonumber(ARGV[4]), ARGV[1])
redis.call('EXPIRE', KEYS[5], ARGV[4])
redis.call('SET', KEYS[4], redis.call('ZCARD', KEYS[5]), 'EX', ARGV[4])
redis.call('LPUSH', KEYS[2], ARGV[1])
return 1
"""

_ACTIVATE = _RECONCILE + """
if redis.call('HGET', KEYS[1], 'user_id') ~= ARGV[2] then return 0 end
if redis.call('HGET', KEYS[1], 'status') == 'complete' then return 0 end
if not redis.call('ZSCORE', KEYS[5], ARGV[1]) then return 0 end
redis.call('HSET', KEYS[1], 'status', 'active')
redis.call('LREM', KEYS[2], 0, ARGV[1])
redis.call('SADD', KEYS[3], ARGV[1])
redis.call('EXPIRE', KEYS[3], ARGV[4])
redis.call('SET', KEYS[4], redis.call('ZCARD', KEYS[5]), 'EX', ARGV[4])
return 1
"""

_COMPLETE = """
if redis.call('HGET', KEYS[1], 'user_id') ~= ARGV[2] then return 0 end
redis.call('HSET', KEYS[1], 'status', 'complete')
redis.call('EXPIRE', KEYS[1], ARGV[4])
redis.call('LREM', KEYS[2], 0, ARGV[1])
redis.call('SREM', KEYS[3], ARGV[1])
redis.call('ZREM', KEYS[5], ARGV[1])
redis.call('SET', KEYS[4], redis.call('ZCARD', KEYS[5]), 'EX', ARGV[4])
return 1
"""


async def _transition(script: str, session_id: str, user_id: str) -> int:
    try:
        return int(await redis_client.client.eval(
            script, 5, _meta_key(session_id), _PENDING_KEY,
            _active_set_key(user_id), _active_count_key(user_id), _reservations_key(user_id),
            session_id, user_id, MAX_CONCURRENT_PER_USER, TASK_META_TTL, _meta_key(''),
            datetime.now(timezone.utc).isoformat()))
    except Exception as exc:
        logger.warning('Task queue transition unavailable (%s)', type(exc).__name__)
        raise QueueUnavailable('Session admission is temporarily unavailable. Try again shortly.') from exc


async def enqueue_session(session_id: str, user_id: str) -> bool:
    """Atomically reserve a pending/active slot; retries keep the original lease."""
    return bool(await _transition(_ADMIT, session_id, user_id))


async def admit_session(session_id: str, user_id: str) -> None:
    """Shared start/resume admission boundary. Never proceed on an unknown result."""
    try:
        if not await enqueue_session(session_id, user_id):
            raise QueueAtCapacity('No session slot is available. Finish or stop a current session, then resume this run.')
        await mark_active(session_id)
    except (QueueAtCapacity, QueueUnavailable):
        raise
    except Exception as exc:
        raise QueueUnavailable('Session admission is temporarily unavailable. Try again shortly.') from exc


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
    """Activate an admitted slot idempotently, without extending its lease."""
    try:
        user_id = await redis_client.client.hget(_meta_key(session_id), 'user_id')
    except Exception as exc:
        raise QueueUnavailable('Session admission is temporarily unavailable. Try again shortly.') from exc
    if not user_id or not await _transition(_ACTIVATE, session_id, user_id):
        raise QueueUnavailable('Session reservation expired or is unavailable. Try again shortly.')


async def mark_complete(session_id: str) -> None:
    """Release this slot exactly once; duplicate completion cannot free another."""
    user_id = await redis_client.client.hget(_meta_key(session_id), 'user_id')
    if user_id:
        await _transition(_COMPLETE, session_id, user_id)


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
    """Count unexpired reservations, including pending work and legacy actives."""
    return await _transition(_RECONCILE + "return redis.call('ZCARD', KEYS[5])", '', user_id)


async def flush_all_active() -> None:
    """Clear all active session counters and sets.

    Explicit administrative reset only. Never call during startup: another
    worker may still own these reservations. Individual leases expire naturally.
    """
    r = redis_client.client
    keys = []
    async for key in r.scan_iter("taskq:active:*"):
        keys.append(key)
    async for key in r.scan_iter("taskq:active_count:*"):
        keys.append(key)
    async for key in r.scan_iter("taskq:meta:*"):
        keys.append(key)
    async for key in r.scan_iter("taskq:reserved:*"):
        keys.append(key)
    # Also clear the pending queue
    keys.append(_PENDING_KEY)
    if keys:
        await r.delete(*keys)
        logger.info("Flushed %d stale task queue keys on startup", len(keys))
