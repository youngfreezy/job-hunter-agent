"""Health-check endpoint."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health_check():
    """Lightweight liveness probe."""
    return {"status": "ok", "version": "0.1.0"}
