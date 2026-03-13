# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""FastAPI gateway for the JobHunter Agent platform.

Provides the REST + SSE API that the Next.js frontend consumes.
Manages the LangGraph pipeline lifecycle, SSE streaming, and HITL flow.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Configure logging for all backend modules (Python default is WARNING only)
_log_fmt = logging.Formatter("%(levelname)s %(name)s: %(message)s")
_console = logging.StreamHandler()
_console.setFormatter(_log_fmt)
_handlers: list[logging.Handler] = [_console]
if os.environ.get("LOG_TO_FILE", "true").lower() == "true":
    _file = logging.FileHandler("backend.log", mode="a")
    _file.setFormatter(_log_fmt)
    _handlers.append(_file)
logging.basicConfig(level=logging.INFO, handlers=_handlers)
for _noisy in (
    "httpcore", "httpx", "neo4j", "urllib3", "watchfiles", "asyncio",
    "browser_use", "cdp_use", "bubus",
    "langgraph.checkpoint.serde.jsonplus",
):
    logging.getLogger(_noisy).setLevel(logging.CRITICAL if _noisy == "bubus" else logging.ERROR)

from backend.shared.config import get_settings
from backend.shared import patches

patches.apply_all()

logger = logging.getLogger(__name__)

# --- Sentry error tracking ---
_settings = get_settings()
if _settings.SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_sdk.init(
            dsn=_settings.SENTRY_DSN,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                LoggingIntegration(level=logging.WARNING, event_level=logging.ERROR),
            ],
            traces_sample_rate=0.1,
            send_default_pii=False,
        )
        logger.info("Sentry initialized")
    except ImportError:
        logger.warning("sentry-sdk not installed — error tracking disabled")


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
        from psycopg import AsyncConnection
        from psycopg_pool import AsyncConnectionPool
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        # Run setup with a dedicated autocommit connection because
        # CREATE INDEX CONCURRENTLY cannot run inside a transaction block.
        try:
            async with await AsyncConnection.connect(
                settings.DATABASE_URL, autocommit=True
            ) as setup_conn:
                setup_saver = AsyncPostgresSaver(setup_conn)
                await setup_saver.setup()
        except Exception as setup_exc:
            logger.warning("Checkpointer setup() failed (%s); tables may already exist", setup_exc)

        pool = AsyncConnectionPool(
            conninfo=settings.DATABASE_URL,
            min_size=2,
            max_size=20,
            open=False,
        )
        await pool.open()
        checkpointer = AsyncPostgresSaver(pool)
        logger.info("Using AsyncPostgresSaver with connection pool")

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

        from backend.shared.autopilot_store import ensure_autopilot_tables
        await ensure_autopilot_tables()

        from backend.shared.agent_store import ensure_agent_tables, seed_builtin_agents
        await ensure_agent_tables()
        seed_builtin_agents()

        try:
            from backend.shared.webhook_store import _ensure_webhook_tables
            _ensure_webhook_tables()
        except Exception as wh_exc:
            logger.warning("Webhook tables setup failed (non-fatal): %s", wh_exc)

        # Schedule daily selector health-check
        from backend.shared.scheduler import schedule, schedule_seconds, schedule_with_notify
        from backend.shared.selector_health import run_selector_health_check
        schedule("selector-health-check", run_selector_health_check, interval_hours=24.0)

        # Schedule daily data cleanup (delete app results older than 90 days)
        from backend.shared.session_store import cleanup_old_data
        schedule("data-cleanup", cleanup_old_data, interval_hours=24.0)

        # Schedule daily cleanup of stale anonymous users (30-day TTL)
        from backend.shared.billing_store import cleanup_anonymous_users
        schedule("anonymous-user-cleanup", cleanup_anonymous_users, interval_hours=24.0)

        # Schedule autopilot checker (LISTEN/NOTIFY + 5min fallback)
        from backend.shared.autopilot_runner import check_and_run_due_schedules
        schedule_with_notify(
            "autopilot-checker",
            check_and_run_due_schedules,
            channel="autopilot_schedules_changed",
            fallback_interval_seconds=300,
        )

        # Schedule Moltbook self-improvement loop (every 30 min)
        if settings.MOLTBOOK_ENABLED and settings.MOLTBOOK_API_KEY:
            from backend.moltbook.cron import run as moltbook_run
            schedule_seconds("moltbook-cron", moltbook_run, interval_seconds=1800, run_immediately=True)
            logger.info("Moltbook cron scheduled (every 30 min)")
        else:
            logger.info("Moltbook integration disabled (MOLTBOOK_ENABLED=%s)", settings.MOLTBOOK_ENABLED)
    except Exception as exc:
        logger.warning(
            "Postgres checkpointer unavailable (%s); falling back to MemorySaver",
            exc,
        )
        pool = None
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()

    graph = build_graph(checkpointer=checkpointer)

    # --- Build Career Pivot graph ---
    from backend.orchestrator.career_pivot.graph import build_career_pivot_graph
    career_pivot_graph = build_career_pivot_graph(checkpointer=checkpointer)

    # --- Build Interview Prep graph ---
    from backend.orchestrator.interview_prep.graph import build_interview_prep_graph
    interview_prep_graph = build_interview_prep_graph(checkpointer=checkpointer)

    # --- Build Freelance Matchmaker graph ---
    from backend.orchestrator.freelance.graph import build_freelance_graph
    freelance_graph = build_freelance_graph(checkpointer=checkpointer)

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
    app.state.career_pivot_graph = career_pivot_graph
    app.state.interview_prep_graph = interview_prep_graph
    app.state.freelance_graph = freelance_graph

    # --- Startup recovery: resume sessions interrupted by previous deploys ---
    from backend.shared.session_store import get_interrupted_sessions
    from backend.gateway.routes.sessions import (
        _resume_stalled_pipeline, _spawn_background,
        session_registry, event_logs,
    )

    # Clear autopilot schedules stuck in is_running=TRUE from dead sessions
    try:
        from backend.shared.autopilot_store import clear_zombie_running
        clear_zombie_running()
    except Exception:
        logger.debug("Failed to clear zombie autopilot schedules", exc_info=True)

    # Mark stale orphaned sessions (>2h old) as failed so they don't sit in limbo
    from backend.shared.db import get_connection as _get_conn
    try:
        with _get_conn() as stale_conn:
            stale_conn.execute(
                """UPDATE sessions SET status = 'failed', updated_at = NOW()
                   WHERE status IN ('intake', 'coaching', 'discovering', 'scoring',
                                    'tailoring', 'applying', 'running', 'interrupted')
                     AND updated_at < NOW() - INTERVAL '2 hours'""",
            )
            stale_conn.commit()
    except Exception:
        logger.debug("Failed to clean up stale sessions", exc_info=True)

    orphaned = get_interrupted_sessions()
    if orphaned:
        logger.info("Found %d interrupted sessions to recover", len(orphaned))
        for sess in orphaned:
            sid = sess["session_id"]
            # Hydrate in-memory registry so SSE reconnects work
            # Include autopilot_schedule_id so mark_run_complete works after recovery
            registry_entry = {
                "session_id": sid,
                "user_id": sess["user_id"],
                "status": "recovering",
            }
            ap_schedule_id = sess.get("autopilot_schedule_id")
            if ap_schedule_id:
                registry_entry["autopilot_schedule_id"] = ap_schedule_id
                registry_entry["is_autopilot"] = True
            session_registry[sid] = registry_entry
            event_logs[sid] = []
            config = {"configurable": {"thread_id": sid}}
            _spawn_background(_resume_stalled_pipeline(sid, graph, config))
            logger.info("Resuming interrupted session %s", sid)

    yield

    # --- Shutdown ---
    logger.info("Shutting down JobHunter gateway")

    # Mark any still-running sessions before exiting
    from backend.gateway.routes.sessions import session_registry as _reg
    from backend.shared.session_store import mark_sessions_interrupted as _mark
    _active = [
        sid for sid, meta in _reg.items()
        if meta.get("status") in {
            "intake", "coaching", "discovering", "scoring",
            "tailoring", "applying", "running", "recovering",
        }
    ]
    if _active:
        logger.info("Shutdown — marking %d sessions as interrupted", len(_active))
        _mark(_active)

    from backend.shared.scheduler import cancel_all
    cancel_all()

    try:
        await redis_client.close()
    except Exception:
        pass

    from backend.shared.db import close_pool
    close_pool()

    if pool is not None:
        await pool.close()
    elif hasattr(checkpointer, "close"):
        await checkpointer.close()


_app_ref: FastAPI | None = None


def create_app() -> FastAPI:
    """Application factory."""
    app = FastAPI(
        title="JobHunter Agent API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # --- CORS ---
    _origins = [
        "http://localhost:3000",
        "https://localhost:3000",
        "http://localhost:3001",
        "https://localhost:3001",
    ]
    _extra_origins = os.environ.get("CORS_ORIGINS", "")
    if _extra_origins:
        _origins.extend(o.strip() for o in _extra_origins.split(",") if o.strip())

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_origin_regex=r"https://(job-hunter-agent(-[a-z0-9]+)?\.vercel\.app|([a-z]+-)+[a-z0-9]+\.up\.railway\.app|([a-z]+\.)?jobhunteragent\.com)",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Starlette middleware execution order is REVERSED from registration.
    # Last registered = first to run on incoming request.
    # Desired request flow: JWT Auth → CSRF → Rate Limiter → Route
    # So register in reverse:

    from backend.gateway.middleware.rate_limit import attach_rate_limiter
    attach_rate_limiter(app)

    from backend.gateway.middleware.csrf import attach_csrf_protection
    attach_csrf_protection(app)

    from backend.gateway.middleware.jwt_auth import attach_jwt_auth
    attach_jwt_auth(app)

    # --- Routes ---
    from backend.gateway.routes.auth import router as auth_router
    from backend.gateway.routes.health import router as health_router
    from backend.gateway.routes.payments import router as payments_router
    from backend.gateway.routes.selectors import router as selectors_router
    from backend.gateway.routes.career_pivot import router as career_pivot_router
    from backend.gateway.routes.interview_prep import router as interview_prep_router
    from backend.gateway.routes.freelance import router as freelance_router
    from backend.gateway.routes.sessions import router as sessions_router
    from backend.gateway.routes.stats import router as stats_router
    from backend.gateway.routes.resume import router as resume_router
    from backend.gateway.routes.autopilot import router as autopilot_router
    from backend.gateway.routes.sms import router as sms_router
    from backend.gateway.routes.free_trial import router as free_trial_router
    from backend.gateway.routes.marketplace import router as marketplace_router
    from backend.gateway.routes.developer import router as developer_router
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(sessions_router)
    app.include_router(payments_router)
    app.include_router(selectors_router)
    app.include_router(career_pivot_router)
    app.include_router(interview_prep_router)
    app.include_router(freelance_router)
    app.include_router(stats_router)
    app.include_router(resume_router)
    app.include_router(autopilot_router)
    app.include_router(sms_router)
    app.include_router(free_trial_router)
    app.include_router(marketplace_router)
    app.include_router(developer_router)

    return app


app = create_app()
_app_ref = app
