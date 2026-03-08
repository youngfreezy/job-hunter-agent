"""Request dependencies for route handlers."""

from fastapi import HTTPException, Request

from backend.shared.billing_store import get_or_create_user


def get_current_user(request: Request) -> dict:
    """Extract user from X-User-Email header, create if needed."""
    email = request.headers.get("X-User-Email")
    if not email:
        raise HTTPException(status_code=401, detail="Authentication required")
    return get_or_create_user(email)
