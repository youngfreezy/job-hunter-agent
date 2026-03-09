# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Redis-backed sliding window rate limiting middleware for FastAPI.

Uses a sliding window counter algorithm with Redis sorted sets to provide
distributed rate limiting. Requests are identified by user ID (from the
``X-User-Id`` header) or by client IP address as a fallback.

Usage::

    from backend.gateway.middleware.rate_limit import attach_rate_limiter

    app = FastAPI()
    attach_rate_limiter(app)
"""

from __future__ import annotations

import logging
import time
from typing import Optional, Tuple

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.shared.redis_client import redis_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Route bucket definitions: (pattern_check, method_filter, max_requests, window_seconds, bucket_name)
# Order matters — first match wins.
# ---------------------------------------------------------------------------

_ROUTE_RULES: list[Tuple[str, Optional[str], int, int, str]] = [
    # Health check — unlimited (handled by early return, listed for clarity)
    ("/api/health", None, 0, 0, "health"),
    # Auth endpoints — tight limits to prevent brute force
    ("/api/auth/login", "POST", 5, 60, "auth_login"),
    ("/api/auth/register", "POST", 3, 60, "auth_register"),
    # Start session — tight limit
    ("/api/sessions", "POST", 2, 60, "session_create"),
    # Test apply — tight limit
    ("/test-apply", "POST", 3, 60, "test_apply"),
    # SSE stream — reconnect-friendly
    ("/stream", "GET", 20, 60, "sse_stream"),
    # Catch-all for other API routes
    ("/api/", None, 60, 60, "api_general"),
]

# Paths that are never rate-limited.
_EXEMPT_PATHS = frozenset({"/api/health", "/health", "/docs", "/openapi.json"})


def _classify_request(path: str, method: str) -> Optional[Tuple[int, int, str]]:
    """Return (max_requests, window_seconds, bucket_name) for a request.

    Returns ``None`` if the route is exempt from rate limiting.
    """
    if path.rstrip("/") in _EXEMPT_PATHS:
        return None

    method_upper = method.upper()

    for pattern, method_filter, max_req, window, bucket in _ROUTE_RULES:
        if pattern == "/api/health":
            continue  # skip — handled above

        # SSE stream: path ends with /stream
        if pattern == "/stream":
            if path.rstrip("/").endswith("/stream") and (
                method_filter is None or method_upper == method_filter
            ):
                return max_req, window, bucket
            continue

        # Auth endpoints: exact path + POST
        if pattern in ("/api/auth/login", "/api/auth/register") and method_filter == "POST":
            if path.rstrip("/") == pattern and method_upper == "POST":
                return max_req, window, bucket
            continue

        # Session create: exact path + POST
        if pattern == "/api/sessions" and method_filter == "POST":
            if path.rstrip("/") == "/api/sessions" and method_upper == "POST":
                return max_req, window, bucket
            continue

        # Test apply: path ends with /test-apply + POST
        if pattern == "/test-apply" and method_filter == "POST":
            if path.rstrip("/").endswith("/test-apply") and method_upper == "POST":
                return max_req, window, bucket
            continue

        # General API catch-all
        if pattern == "/api/" and path.startswith("/api/"):
            return max_req, window, bucket

    # Non-API routes (frontend proxied, static, etc.) — no limit
    return None


def _get_identifier(request: Request) -> str:
    """Determine the rate-limit identity for the request.

    Uses the authenticated user email (set by JWT middleware) when available,
    falling back to the client's IP address. Never trusts client-supplied
    headers for identity to prevent rate-limit bypass.
    """
    # Use authenticated identity from JWT middleware (not spoofable)
    user_email = getattr(request.state, "user_email", None)
    if user_email:
        return f"user:{user_email}"

    # Use X-Forwarded-For if behind a reverse proxy, otherwise use client host.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"
    return f"ip:{ip}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that enforces per-user/IP sliding window rate limits
    backed by Redis sorted sets.

    Algorithm (sliding window counter with sorted sets):
        1. Key: ``ratelimit:{identifier}:{bucket}``
        2. Each request adds a member with score = current timestamp.
        3. Remove all members with score < (now - window).
        4. Count remaining members.
        5. If count >= limit, reject with 429.
        6. Set key TTL = window so stale keys auto-expire.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        method = request.method

        classification = _classify_request(path, method)
        if classification is None:
            return await call_next(request)

        max_requests, window_seconds, bucket = classification
        identifier = _get_identifier(request)

        try:
            allowed, retry_after = await self._check_rate_limit(
                identifier, bucket, max_requests, window_seconds
            )
        except Exception:
            # If Redis is down, allow the request through rather than blocking
            # all traffic.  Log the error so it can be investigated.
            logger.exception("Rate limiter Redis error — allowing request")
            return await call_next(request)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too Many Requests",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)

        # Attach informational rate-limit headers.
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Bucket"] = bucket
        return response

    # ------------------------------------------------------------------
    # Core sliding window implementation
    # ------------------------------------------------------------------

    @staticmethod
    async def _check_rate_limit(
        identifier: str,
        bucket: str,
        max_requests: int,
        window_seconds: int,
    ) -> Tuple[bool, int]:
        """Check and record a request against the rate limit.

        Returns
        -------
        (allowed, retry_after)
            *allowed* is ``True`` if the request should proceed.
            *retry_after* is the number of seconds the client should wait
            before retrying (only meaningful when *allowed* is ``False``).
        """
        now = time.time()
        window_start = now - window_seconds
        key = f"ratelimit:{identifier}:{bucket}"

        redis = redis_client.client
        pipe = redis.pipeline(transaction=True)

        # 1. Remove expired entries
        pipe.zremrangebyscore(key, "-inf", window_start)
        # 2. Count current entries
        pipe.zcard(key)
        # 3. Add current request (unique member via timestamp + random-ish suffix)
        member = f"{now}"
        pipe.zadd(key, {member: now})
        # 4. Set TTL so the key self-cleans
        pipe.expire(key, window_seconds)

        results = await pipe.execute()
        # results[1] is the count BEFORE we added the new entry
        current_count = results[1]

        if current_count >= max_requests:
            # Already at the limit — remove the entry we just added
            await redis.zrem(key, member)

            # Calculate when the oldest entry in the window will expire
            oldest = await redis.zrange(key, 0, 0, withscores=True)
            if oldest:
                oldest_score = oldest[0][1]
                retry_after = max(1, int(oldest_score + window_seconds - now) + 1)
            else:
                retry_after = window_seconds
            return False, retry_after

        return True, 0


def attach_rate_limiter(app: FastAPI) -> None:
    """Convenience function to add the rate-limit middleware to *app*.

    Call this after adding CORS middleware so rate limiting runs first
    (middleware execution order is LIFO in Starlette).
    """
    app.add_middleware(RateLimitMiddleware)
