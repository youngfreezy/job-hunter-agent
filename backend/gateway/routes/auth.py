# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Authentication routes.

NextAuth handles authentication on the frontend (Next.js) via OAuth providers.
This module provides /api/auth/me to resolve the backend user from the JWT
token set by JWTAuthMiddleware, plus account management endpoints.
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.gateway.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Authenticated endpoints
# ---------------------------------------------------------------------------

@router.get("/me")
async def me(request: Request):
    """Return the current user resolved from JWT authentication."""
    user = get_current_user(request)
    return {"user": user}


class NotificationChannelUpdate(BaseModel):
    notification_channel: str


@router.put("/me/notification-channel")
async def update_notification_channel(request: Request, body: NotificationChannelUpdate):
    """Update the user's notification channel preference (email, sms, or both)."""
    user = get_current_user(request)
    if body.notification_channel not in ("email", "sms", "both"):
        return JSONResponse(status_code=400, content={"detail": "Invalid channel. Must be email, sms, or both."})
    from backend.shared.billing_store import update_notification_channel as _update_channel
    _update_channel(user["id"], body.notification_channel)
    return {"notification_channel": body.notification_channel}


class BlockedCompaniesUpdate(BaseModel):
    blocked_companies: list[str]


@router.get("/me/blocked-companies")
async def get_blocked_companies(request: Request):
    """Return the user's blocked companies list."""
    user = get_current_user(request)
    from backend.shared.billing_store import get_user_by_id
    user_data = get_user_by_id(user["id"])
    return {"blocked_companies": user_data.get("blocked_companies", []) if user_data else []}


@router.put("/me/blocked-companies")
async def update_blocked_companies(request: Request, body: BlockedCompaniesUpdate):
    """Update the user's blocked companies list."""
    user = get_current_user(request)
    from backend.shared.billing_store import update_blocked_companies as _update_blocked
    _update_blocked(user["id"], body.blocked_companies)
    return {"blocked_companies": body.blocked_companies}


class ApplicationRulesUpdate(BaseModel):
    application_rules: str


@router.get("/me/application-rules")
async def get_application_rules(request: Request):
    """Return the owner's free-text application rules (empty string when unset)."""
    user = get_current_user(request)
    from backend.shared.billing_store import get_application_rules as _get_rules
    return {"application_rules": _get_rules(user["id"])}


@router.put("/me/application-rules")
async def update_application_rules(request: Request, body: ApplicationRulesUpdate):
    """Replace the owner's application rules. Injected into scoring and form filling."""
    from backend.shared.application_rules import MAX_RULES_CHARS

    user = get_current_user(request)
    rules = body.application_rules.strip()
    if len(rules) > MAX_RULES_CHARS:
        return JSONResponse(
            status_code=400,
            content={"detail": f"Application rules must be at most {MAX_RULES_CHARS} characters."},
        )
    from backend.shared.billing_store import update_application_rules as _update_rules
    _update_rules(user["id"], rules)
    return {"application_rules": rules}


class MinimumSubmittedUpdate(BaseModel):
    minimum_submitted_applications: int


@router.put("/me/minimum-submitted")
async def update_minimum_submitted(request: Request, body: MinimumSubmittedUpdate):
    """Update the user's default minimum submitted applications preference. Premium only."""
    user = get_current_user(request)
    if not user.get("is_premium", False):
        return JSONResponse(status_code=403, content={"detail": "Premium feature only."})
    if body.minimum_submitted_applications < 0 or body.minimum_submitted_applications > 20:
        return JSONResponse(status_code=400, content={"detail": "Must be between 0 and 20."})
    from backend.shared.billing_store import update_minimum_submitted as _update_min
    _update_min(user["id"], body.minimum_submitted_applications)
    return {"minimum_submitted_applications": body.minimum_submitted_applications}


@router.delete("/me/data")
async def delete_user_data(request: Request):
    """GDPR: permanently delete all data associated with the current user."""
    from backend.gateway.routes.sessions import session_registry
    from backend.shared.billing_store import delete_user_data as delete_billing_data
    from backend.shared.redis_client import redis_client
    from backend.shared.session_store import get_session_ids_for_user
    from backend.shared.data_deletion import ActiveWorkDeletionError, require_idle_sessions

    user = get_current_user(request)
    user_id = user["id"]
    logger.info("Account data delete requested for user %s", user_id)

    # Resolve durable ownership before deletion, including sessions not in memory.
    try:
        stored_session_ids = get_session_ids_for_user(str(user_id), require_stopped=True)
    except ActiveWorkDeletionError:
        raise HTTPException(status_code=409, detail="Stop queued and active sessions before deleting their data.") from None
    except Exception:
        raise HTTPException(status_code=503, detail="Account data deletion is temporarily unavailable") from None
    user_session_ids = sorted(set(stored_session_ids) | {
        sid
        for sid, meta in session_registry.items()
        if str(meta.get("user_id")) == str(user_id)
    })

    # Stop must settle workers and queue admission before credentials/data vanish.
    from backend.shared.model_key_store import save_model_key
    try:
        await require_idle_sessions(str(user_id), user_session_ids, entire_account=True)
        save_model_key(str(user_id), "")
    except ActiveWorkDeletionError:
        raise HTTPException(status_code=409, detail="Stop queued and active sessions before deleting their data.") from None
    except Exception:
        raise HTTPException(status_code=503, detail="Account data deletion is temporarily unavailable") from None

    # All owned database records are erased in one transaction.
    try:
        billing_deleted = delete_billing_data(user_id)
    except ActiveWorkDeletionError:
        raise HTTPException(status_code=409, detail="Stop queued and active sessions before deleting their data.") from None
    if not billing_deleted:
        raise HTTPException(status_code=503, detail="Account data deletion is temporarily unavailable")

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
        from backend.gateway.middleware.rate_limit import clear_user_rate_limits
        redis_keys_deleted += await clear_user_rate_limits(user["email"])
    except Exception:
        logger.exception("Failed to clear rate-limit keys for user %s", user_id)

    # Screenshots/checkpoints/resumes were included in the database transaction.
    for sid in user_session_ids:
        session_registry.pop(sid, None)

    return JSONResponse(
        status_code=200,
        content={
            "deleted": True,
            "user_id": user_id,
            "sessions_cleared": len(user_session_ids),
            "redis_keys_deleted": redis_keys_deleted,
            "billing_deleted": billing_deleted,
            "application_results_deleted": True,
        },
    )
