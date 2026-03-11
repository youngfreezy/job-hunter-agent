# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""CSRF protection middleware using double-submit cookie pattern.

For state-changing requests (POST, PUT, PATCH, DELETE), validates that
the X-CSRF-Token header matches the csrf_token cookie. The token is
set on every response as a secure cookie.

GET/HEAD/OPTIONS requests are exempt (they should be side-effect-free).
SSE streaming endpoints are exempt (they are read-only by nature).
Webhook endpoints are exempt (they use signature verification instead).
"""

from __future__ import annotations

import hmac
import logging
import secrets

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_EXEMPT_PATHS = {
    "/api/health",
    "/api/health/ready",
    "/api/stripe/webhook",
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/link-google",
}
_EXEMPT_PREFIXES = (
    "/api/sessions/",  # SSE stream endpoints use GET
    "/api/free-trial/",  # Unauthenticated trial endpoints (no session to hijack)
)
_COOKIE_NAME = "csrf_token"
_HEADER_NAME = "x-csrf-token"


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit cookie CSRF protection."""

    async def dispatch(self, request: Request, call_next):
        # Set CSRF token cookie on every response if not present
        csrf_cookie = request.cookies.get(_COOKIE_NAME)
        if not csrf_cookie:
            csrf_cookie = secrets.token_urlsafe(32)

        # Skip validation for safe methods
        if request.method in _SAFE_METHODS:
            response = await call_next(request)
            response.set_cookie(
                _COOKIE_NAME,
                csrf_cookie,
                httponly=False,  # JS needs to read this
                samesite="lax",
                secure=request.url.scheme == "https",
                max_age=86400,
            )
            return response

        # Skip validation for exempt paths
        path = request.url.path
        if path in _EXEMPT_PATHS or path.rstrip("/") in _EXEMPT_PATHS:
            response = await call_next(request)
            return response

        # Skip validation for exempt prefixes
        if path.startswith(_EXEMPT_PREFIXES):
            response = await call_next(request)
            return response

        # Skip validation for Skyvern-facing endpoints (service-to-service,
        # no browser cookies). These use HMAC signature verification instead.
        if path.endswith("/totp-code") or "/resume-file" in path:
            response = await call_next(request)
            return response

        # If the request was authenticated via JWT (Bearer token), skip CSRF
        # validation. Bearer tokens are not auto-attached by the browser, so
        # they inherently prevent CSRF (attacker can't forge the Authorization
        # header from a cross-origin page).
        if getattr(request.state, "user_email", None):
            response = await call_next(request)
            return response

        # Validate CSRF token for state-changing requests without JWT
        header_token = request.headers.get(_HEADER_NAME)
        if not header_token or not hmac.compare_digest(header_token, csrf_cookie):
            logger.warning(
                "CSRF validation failed for %s %s (cookie=%s, header=%s)",
                request.method,
                path,
                bool(csrf_cookie),
                bool(header_token),
            )
            return Response(
                content='{"detail":"CSRF token missing or invalid"}',
                status_code=403,
                media_type="application/json",
            )

        response = await call_next(request)
        response.set_cookie(
            _COOKIE_NAME,
            csrf_cookie,
            httponly=False,
            samesite="lax",
            secure=request.url.scheme == "https",
            max_age=86400,
        )
        return response


def attach_csrf_protection(app: FastAPI) -> None:
    """Add CSRF middleware to the FastAPI app."""
    app.add_middleware(CSRFMiddleware)
    logger.info("CSRF protection middleware attached")
