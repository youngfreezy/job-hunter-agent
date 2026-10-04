# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Request dependencies for route handlers."""

import logging

from fastapi import HTTPException, Request

from backend.shared.billing_store import get_or_create_user

logger = logging.getLogger(__name__)


def get_current_user(request: Request) -> dict:
    """Extract user from JWT-validated email (set by JWTAuthMiddleware).

    Anonymous trial tokens are no longer an authentication mechanism.
    """
    email = getattr(request.state, "user_email", None)

    if email:
        from backend.shared.model_access import bind_model_user
        user = get_or_create_user(email)
        bind_model_user(str(user["id"]))
        return user

    raise HTTPException(status_code=401, detail="Authentication required")


def get_model_user(request: Request) -> dict:
    """Authenticate and reject unfunded model work before launching a task."""
    from backend.shared.model_access import require_model_access
    user = get_current_user(request)
    require_model_access(str(user["id"]))
    return user


def get_owned_registry_session(request: Request, registry: dict, session_id: str) -> dict:
    """Authorize auxiliary in-memory reports before reads, events, or mutation."""
    user = get_current_user(request)
    meta = registry.get(session_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if str(meta.get("user_id")) != str(user["id"]):
        raise HTTPException(status_code=403, detail="Not your session")
    return meta


async def verify_session_owner(session_id: str, user: dict, request: Request) -> None:
    """Verify the authenticated user owns the given session.

    Checks the in-memory session_registry first, then falls back to the
    checkpointer's stored user_id in the graph state.
    Raises 403 if the user doesn't own the session, 404 if not found.
    """
    from backend.gateway.routes.sessions import session_registry

    # Check in-memory registry first
    meta = session_registry.get(session_id)
    if meta:
        owner_id = meta.get("user_id")
        if owner_id and str(owner_id) != str(user["id"]):
            raise HTTPException(status_code=403, detail="Not your session")
        if owner_id:
            return  # Ownership confirmed

    # Durable ownership survives restarts even when no checkpoint was written.
    from backend.shared.session_store import get_session_by_id
    try:
        stored = get_session_by_id(session_id)
    except Exception:
        raise HTTPException(status_code=503, detail="Session ownership is temporarily unavailable")
    if stored:
        owner_id = stored.get("user_id")
        if not owner_id or str(owner_id) != str(user["id"]):
            raise HTTPException(status_code=403, detail="Not your session")
        return

    # Fall back to checkpointer (session may have been recovered after restart)
    checkpointer = getattr(request.app.state, "checkpointer", None)
    if checkpointer:
        try:
            config = {"configurable": {"thread_id": session_id}}
            state = await checkpointer.aget(config)
            if state is not None:
                cp = state
                if hasattr(state, "checkpoint"):
                    cp = state.checkpoint
                cv = cp.get("channel_values", cp) if isinstance(cp, dict) else {}
                if isinstance(cv, dict):
                    owner_id = cv.get("user_id")
                    if owner_id and str(owner_id) != str(user["id"]):
                        raise HTTPException(status_code=403, detail="Not your session")
                    if owner_id:
                        return  # Ownership confirmed
        except HTTPException:
            raise
        except Exception:
            logger.debug("Failed to check session ownership via checkpointer", exc_info=True)

    raise HTTPException(status_code=404, detail="Session not found")
