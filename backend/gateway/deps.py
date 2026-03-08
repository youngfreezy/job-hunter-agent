"""Request dependencies for route handlers."""

import logging

from fastapi import HTTPException, Request

from backend.shared.billing_store import get_or_create_user

logger = logging.getLogger(__name__)


def get_current_user(request: Request) -> dict:
    """Extract user from JWT-validated email (set by JWTAuthMiddleware).

    Falls back to X-User-Email header for backward compatibility during
    migration, but logs a deprecation warning.
    """
    # Primary: email extracted from NextAuth JWT by middleware
    email = getattr(request.state, "user_email", None)

    if not email:
        raise HTTPException(status_code=401, detail="Authentication required")

    return get_or_create_user(email)
