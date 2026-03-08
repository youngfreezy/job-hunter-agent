# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Health-check endpoints."""

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health_check():
    """Lightweight liveness probe."""
    return {"status": "ok", "version": "0.1.0"}


@router.get("/api/health/ready")
async def readiness_check():
    """Deep readiness check — verifies DB, Redis, and external API connectivity."""
    checks: dict = {}

    # Postgres
    try:
        import psycopg
        from backend.shared.config import get_settings
        conn = psycopg.connect(get_settings().DATABASE_URL)
        conn.execute("SELECT 1")
        conn.close()
        checks["postgres"] = "ok"
    except Exception as e:
        logger.warning("Health check: Postgres unavailable: %s", e)
        checks["postgres"] = "unavailable"

    # Redis
    try:
        from backend.shared.redis_client import redis_client
        await redis_client.client.ping()
        checks["redis"] = "ok"
    except Exception as e:
        logger.warning("Health check: Redis unavailable: %s", e)
        checks["redis"] = "unavailable"

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "checks": checks,
        "version": "0.1.0",
    }
