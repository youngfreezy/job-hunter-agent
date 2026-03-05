"""FastAPI gateway for the JobHunter Agent platform.

Provides the REST + SSE API that the Next.js frontend consumes.
Manages the LangGraph pipeline lifecycle, SSE streaming, and HITL flow.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.shared.config import get_settings

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

    # --- Checkpointer: prefer Postgres, fall back to in-memory ---
    checkpointer = None
    pg_conn = None
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        # Newer langgraph versions return an async context manager
        pg_conn = AsyncPostgresSaver.from_conn_string(settings.DATABASE_URL)
        checkpointer = await pg_conn.__aenter__()
        await checkpointer.setup()
        logger.info("Using AsyncPostgresSaver (dsn=%s...)", settings.DATABASE_URL[:40])
    except Exception as exc:
        logger.warning(
            "Postgres checkpointer unavailable (%s); falling back to MemorySaver",
            exc,
        )
        pg_conn = None
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()

    graph = build_graph(checkpointer=checkpointer)

    # Attach to app.state so route handlers can access them
    app.state.graph = graph
    app.state.checkpointer = checkpointer
    app.state.settings = settings

    yield

    # --- Shutdown ---
    logger.info("Shutting down JobHunter gateway")
    if pg_conn is not None:
        await pg_conn.__aexit__(None, None, None)
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

    # --- Routes ---
    from backend.gateway.routes.auth import router as auth_router
    from backend.gateway.routes.health import router as health_router
    from backend.gateway.routes.payments import router as payments_router
    from backend.gateway.routes.sessions import router as sessions_router

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(sessions_router)
    app.include_router(payments_router)

    return app


app = create_app()
