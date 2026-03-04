"""Redis connection manager for pub/sub, caching, and screenshot streaming.

Wraps ``redis.asyncio`` with connection pooling, pub/sub helpers, and
simple get/set caching.  Used by the screenshot streamer, SSE gateway,
and general-purpose caching throughout the platform.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Optional

import redis.asyncio as aioredis

from backend.shared.config import get_settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Async Redis wrapper with connection pooling, pub/sub, and caching."""

    def __init__(self, url: Optional[str] = None) -> None:
        self._url = url or get_settings().REDIS_URL
        self._pool: Optional[aioredis.ConnectionPool] = None
        self._redis: Optional[aioredis.Redis] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Create the connection pool and Redis client."""
        if self._redis is not None:
            return
        self._pool = aioredis.ConnectionPool.from_url(
            self._url,
            max_connections=20,
            decode_responses=True,
        )
        self._redis = aioredis.Redis(connection_pool=self._pool)
        logger.info("Redis connected to %s", self._url)

    async def close(self) -> None:
        """Gracefully shut down the connection pool."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        if self._pool is not None:
            await self._pool.disconnect()
            self._pool = None
        logger.info("Redis connection closed")

    @property
    def client(self) -> aioredis.Redis:
        """Return the underlying Redis client, connecting lazily if needed."""
        if self._redis is None:
            raise RuntimeError(
                "RedisClient not connected. Call await redis_client.connect() first."
            )
        return self._redis

    # ------------------------------------------------------------------
    # Pub / Sub
    # ------------------------------------------------------------------

    async def publish_event(self, channel: str, data: Any) -> int:
        """Publish a JSON-serialised event to *channel*.

        Parameters
        ----------
        channel:
            Redis pub/sub channel name (e.g. ``screenshots:{session_id}``).
        data:
            Any JSON-serialisable payload.

        Returns
        -------
        int
            Number of subscribers that received the message.
        """
        payload = json.dumps(data) if not isinstance(data, str) else data
        result = await self.client.publish(channel, payload)
        return result

    async def subscribe(self, channel: str) -> aioredis.client.PubSub:
        """Subscribe to *channel* and return the PubSub object.

        Caller is responsible for iterating over messages and calling
        ``pubsub.unsubscribe()`` / ``pubsub.aclose()`` when done.
        """
        pubsub = self.client.pubsub()
        await pubsub.subscribe(channel)
        logger.debug("Subscribed to Redis channel: %s", channel)
        return pubsub

    async def listen(self, channel: str) -> AsyncIterator[dict]:
        """Convenience async generator that yields parsed messages from *channel*.

        Yields dicts with keys ``type``, ``channel``, ``data``.  Only
        ``message`` type events are yielded (subscriptions confirmations
        are filtered out).
        """
        pubsub = await self.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                raw = message["data"]
                try:
                    parsed = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    parsed = raw
                yield {
                    "type": message["type"],
                    "channel": message["channel"],
                    "data": parsed,
                }
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    # ------------------------------------------------------------------
    # Simple key/value caching
    # ------------------------------------------------------------------

    async def get(self, key: str) -> Optional[str]:
        """Get a cached value by key.  Returns ``None`` if not found."""
        return await self.client.get(key)

    async def set(
        self,
        key: str,
        value: str,
        expire_seconds: Optional[int] = None,
    ) -> None:
        """Set a cached value, optionally with a TTL in seconds."""
        if expire_seconds is not None:
            await self.client.setex(key, expire_seconds, value)
        else:
            await self.client.set(key, value)

    async def delete(self, key: str) -> None:
        """Delete a cached key."""
        await self.client.delete(key)

    async def exists(self, key: str) -> bool:
        """Check whether *key* exists."""
        return bool(await self.client.exists(key))

    # ------------------------------------------------------------------
    # JSON helpers (convenience wrappers)
    # ------------------------------------------------------------------

    async def get_json(self, key: str) -> Optional[Any]:
        """Get and JSON-decode a cached value."""
        raw = await self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    async def set_json(
        self,
        key: str,
        value: Any,
        expire_seconds: Optional[int] = None,
    ) -> None:
        """JSON-encode and cache a value."""
        await self.set(key, json.dumps(value), expire_seconds=expire_seconds)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

redis_client = RedisClient()
