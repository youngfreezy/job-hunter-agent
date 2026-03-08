"""Authentication routes.

NextAuth handles authentication on the frontend (Next.js).
This module provides /api/auth/me to resolve the backend user
from the X-User-Email header sent by the frontend.
"""

from fastapi import APIRouter, Request

from backend.gateway.deps import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me")
async def me(request: Request):
    """Return the current user resolved from X-User-Email header."""
    user = get_current_user(request)
    return {"user": user}
