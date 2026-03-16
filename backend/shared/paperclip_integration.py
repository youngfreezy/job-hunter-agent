# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Paperclip integration — wraps existing async agents with heartbeat reporting.

Does NOT replace any existing logic. Adds observability by reporting
each cron/scheduler run to Paperclip's dashboard as an activity event
with duration, status, and cost tracking.

When PAPERCLIP_ENABLED=false, all functions are no-ops.
"""

from __future__ import annotations

import logging
import os
import time
from functools import wraps
from typing import Callable

from backend.shared.config import get_settings

logger = logging.getLogger(__name__)

_initialized = False


def init_paperclip() -> bool:
    """Initialize Paperclip client with agent credentials from env vars.

    Call once during app startup. Returns True if Paperclip is enabled and configured.

    Env vars (set in .env):
        PAPERCLIP_ENABLED=true
        PAPERCLIP_API_URL=http://127.0.0.1:3100/api
        PAPERCLIP_COMPANY_ID=<company-uuid>
        PAPERCLIP_AGENT_MOLTBOOK=<agent-id>:<token>
        PAPERCLIP_AGENT_AUTOPILOT=<agent-id>:<token>
        PAPERCLIP_AGENT_CLEANUP=<agent-id>:<token>
        PAPERCLIP_AGENT_HEALTH=<agent-id>:<token>
    """
    global _initialized

    settings = get_settings()
    if not settings.PAPERCLIP_ENABLED:
        return False

    if _initialized:
        return True

    from backend.shared.paperclip_client import configure_agents

    # Pydantic Settings loads .env for its own fields, but PAPERCLIP_AGENT_*
    # are not in Settings — load .env into os.environ for these
    from dotenv import load_dotenv
    load_dotenv()

    agents = {}
    for name, env_key in [
        ("moltbook", "PAPERCLIP_AGENT_MOLTBOOK"),
        ("autopilot", "PAPERCLIP_AGENT_AUTOPILOT"),
        ("cleanup", "PAPERCLIP_AGENT_CLEANUP"),
        ("health-check", "PAPERCLIP_AGENT_HEALTH"),
    ]:
        val = os.environ.get(env_key, "")
        if ":" in val:
            agent_id, token = val.split(":", 1)
            agents[name] = {"id": agent_id, "token": token}

    if agents:
        configure_agents(agents)
        _initialized = True
        logger.info("Paperclip integration initialized with %d agents", len(agents))
        return True
    else:
        logger.warning("Paperclip enabled but no agent credentials found in env")
        return False


def with_paperclip_reporting(agent_name: str):
    """Decorator that wraps an async cron function with Paperclip heartbeat reporting.

    Usage:
        @with_paperclip_reporting("moltbook")
        async def run_moltbook():
            ...  # existing logic unchanged
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            settings = get_settings()

            # If Paperclip not enabled, just run the original function
            if not settings.PAPERCLIP_ENABLED or not _initialized:
                return await func(*args, **kwargs)

            from backend.shared.paperclip_client import report_heartbeat

            start = time.monotonic()
            error_msg = None
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as exc:
                error_msg = str(exc)[:500]
                raise
            finally:
                duration = time.monotonic() - start
                try:
                    report_heartbeat(
                        agent_name=agent_name,
                        status="completed" if error_msg is None else "failed",
                        summary=f"{func.__name__} ran in {duration:.1f}s",
                        duration_seconds=duration,
                        error=error_msg,
                    )
                except Exception:
                    logger.debug("Paperclip heartbeat report failed for %s", agent_name, exc_info=True)

        return wrapper
    return decorator
