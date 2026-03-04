"""Authentication routes (stub).

NextAuth handles authentication on the frontend (Next.js).
This module provides a development-only /api/auth/me endpoint
and will be expanded if server-side token verification is needed.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me")
async def me():
    """Return the current user.  Stub for local development."""
    return {"user": "test-user"}
