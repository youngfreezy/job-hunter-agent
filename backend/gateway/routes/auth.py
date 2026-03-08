# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Authentication routes.

NextAuth handles authentication on the frontend (Next.js).
This module provides /api/auth/me to resolve the backend user
from the JWT token set by JWTAuthMiddleware.
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.gateway.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me")
async def me(request: Request):
    """Return the current user resolved from JWT authentication."""
    user = get_current_user(request)
    return {"user": user}


@router.delete("/me/data")
async def delete_user_data(request: Request):
    """GDPR: permanently delete all data associated with the current user."""
    from backend.gateway.routes.sessions import session_registry
    from backend.shared.application_store import delete_application_results_for_sessions
    from backend.shared.billing_store import delete_user_data as delete_billing_data
    from backend.shared.redis_client import redis_client

    user = get_current_user(request)
    user_id = user["id"]
    user_email = user["email"]
    logger.info("GDPR delete requested for user %s (%s)", user_id, user_email)

    # 1. Collect session IDs owned by this user
    user_session_ids = [
        sid
        for sid, meta in session_registry.items()
        if meta.get("user_id") == user_id
    ]

    # 2. Delete application results for those sessions
    app_deleted = delete_application_results_for_sessions(user_session_ids)

    # 3. Delete billing data (wallet_transactions + users row)
    billing_deleted = delete_billing_data(user_id)

    # 4. Clear Redis keys for this user's sessions (gmail tokens)
    redis_keys_deleted = 0
    for sid in user_session_ids:
        try:
            await redis_client.delete(f"gmail_token:{sid}")
            redis_keys_deleted += 1
        except Exception:
            logger.exception("Failed to delete gmail_token for session %s", sid)

    # 5. Clear rate-limit keys for this user
    try:
        rl_pattern = f"ratelimit:user:{user_id}:*"
        keys = await redis_client.client.keys(rl_pattern)
        if keys:
            await redis_client.client.delete(*keys)
            redis_keys_deleted += len(keys)
    except Exception:
        logger.exception("Failed to clear rate-limit keys for user %s", user_id)

    # 6. Remove sessions from in-memory registry
    for sid in user_session_ids:
        session_registry.pop(sid, None)

    success = app_deleted and billing_deleted
    status_code = 200 if success else 207

    return JSONResponse(
        status_code=status_code,
        content={
            "deleted": True,
            "user_id": user_id,
            "sessions_cleared": len(user_session_ids),
            "redis_keys_deleted": redis_keys_deleted,
            "billing_deleted": billing_deleted,
            "application_results_deleted": app_deleted,
        },
    )
