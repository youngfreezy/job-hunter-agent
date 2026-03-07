"""FastAPI gateway for the JobHunter Agent platform.

Provides the REST + SSE API that the Next.js frontend consumes.
Manages the LangGraph pipeline lifecycle, SSE streaming, and HITL flow.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Configure logging for all backend modules (Python default is WARNING only)
_log_fmt = logging.Formatter("%(levelname)s %(name)s: %(message)s")
_console = logging.StreamHandler()
_console.setFormatter(_log_fmt)
_file = logging.FileHandler("backend.log", mode="a")
_file.setFormatter(_log_fmt)
logging.basicConfig(level=logging.INFO, handlers=[_console, _file])
for _noisy in (
    "httpcore", "httpx", "neo4j", "urllib3", "watchfiles", "asyncio",
    "browser_use", "cdp_use", "bubus",
):
    logging.getLogger(_noisy).setLevel(logging.CRITICAL if _noisy == "bubus" else logging.ERROR)

from backend.shared.config import get_settings
from backend.shared import patches

patches.apply_all()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle.

    1. Load settings
    2. Build the LangGraph graph
    3. Set up AsyncPostgresSaver checkpointer (MemorySaver fallback)
    4. Attach graph + checkpointer to app.state
    """
    settings = get_settings()
    logger.info("Starting JobHunter gateway (log_level=%s)", settings.LOG_LEVEL)

    # --- Build the LangGraph pipeline ---
    from backend.orchestrator.pipeline.graph import build_graph  # noqa: E402

    # --- Checkpointer: prefer Postgres connection POOL, fall back to in-memory ---
    # IMPORTANT: Must use a connection POOL (not a single connection) because
    # graph.astream writes checkpoints while other requests (getSession,
    # coach-review) read concurrently.  A single psycopg async connection
    # serialises all queries, deadlocking the entire event loop.
    checkpointer = None
    pool = None
    try:
        from psycopg_pool import AsyncConnectionPool
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        pool = AsyncConnectionPool(
            conninfo=settings.DATABASE_URL,
            min_size=2,
            max_size=10,
            open=False,
        )
        await pool.open()
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()
        logger.info("Using AsyncPostgresSaver with pool (dsn=%s...)", settings.DATABASE_URL[:40])

        # Ensure selector tables exist and seed defaults
        from backend.shared.selector_memory import (
            ensure_table,
            seed_defaults as seed_discovery_defaults,
        )
        await ensure_table()
        await seed_discovery_defaults()

        from backend.browser.tools.apply_selectors import (
            ensure_table as ensure_apply_table,
            seed_defaults as seed_apply_defaults,
        )
        await ensure_apply_table()
        await seed_apply_defaults()

        from backend.shared.application_store import ensure_table as ensure_app_table
        await ensure_app_table()

        from backend.shared.billing_store import ensure_billing_tables
        await ensure_billing_tables()

        # Schedule daily selector health-check
        from backend.shared.scheduler import schedule
        from backend.shared.selector_health import run_selector_health_check
        schedule("selector-health-check", run_selector_health_check, interval_hours=24.0)
    except Exception as exc:
        logger.warning(
            "Postgres checkpointer unavailable (%s); falling back to MemorySaver",
            exc,
        )
        pool = None
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()

    graph = build_graph(checkpointer=checkpointer)

    # --- Redis ---
    from backend.shared.redis_client import redis_client
    try:
        await redis_client.connect()
        # Clear stale task queue counters from previous runs
        from backend.shared.task_queue import flush_all_active
        await flush_all_active()
    except Exception as exc:
        logger.warning("Redis connection failed (%s) — rate limiting and task queue disabled", exc)

    # Attach to app.state so route handlers can access them
    app.state.graph = graph
    app.state.checkpointer = checkpointer
    app.state.settings = settings

    yield

    # --- Shutdown ---
    logger.info("Shutting down JobHunter gateway")
    from backend.shared.scheduler import cancel_all
    cancel_all()

    try:
        await redis_client.close()
    except Exception:
        pass

    if pool is not None:
        await pool.close()
    elif hasattr(checkpointer, "close"):
        await checkpointer.close()


def create_app() -> FastAPI:
    """Application factory."""
    app = FastAPI(
        title="JobHunter Agent API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # --- CORS ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "https://localhost:3000",
        ],
        allow_origin_regex=r"https://.*\.vercel\.app",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Rate Limiting (runs after CORS in middleware stack) ---
    from backend.gateway.middleware.rate_limit import attach_rate_limiter
    attach_rate_limiter(app)

    # --- Routes ---
    from backend.gateway.routes.auth import router as auth_router
    from backend.gateway.routes.health import router as health_router
    from backend.gateway.routes.payments import router as payments_router
    from backend.gateway.routes.selectors import router as selectors_router
    from backend.gateway.routes.sessions import router as sessions_router
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(sessions_router)
    app.include_router(payments_router)
    app.include_router(selectors_router)

    return app


app = create_app()
