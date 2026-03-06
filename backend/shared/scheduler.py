"""Lightweight async periodic scheduler — no external deps.

Usage during app startup::

    from backend.shared.scheduler import schedule, cancel_all
    schedule("selector-health-check", run_health_check, interval_hours=24.0)
    # on shutdown:
    cancel_all()
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_tasks: dict[str, asyncio.Task] = {}


async def _run_periodic(name: str, coro_factory, interval_hours: float):
    """Run *coro_factory()* every *interval_hours*."""
    while True:
        try:
            await asyncio.sleep(interval_hours * 3600)
            logger.info("Scheduler: running %s", name)
            await coro_factory()
            logger.info("Scheduler: %s completed", name)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Scheduler: %s failed", name)


def schedule(name: str, coro_factory, interval_hours: float = 24.0):
    """Register a periodic task. Call during app startup."""
    if name in _tasks:
        logger.warning("Scheduler: %s already registered, skipping", name)
        return
    task = asyncio.create_task(_run_periodic(name, coro_factory, interval_hours))
    _tasks[name] = task
    logger.info("Scheduler: registered %s (every %.1fh)", name, interval_hours)


def cancel_all():
    """Cancel all scheduled tasks. Call during app shutdown."""
    for name, task in _tasks.items():
        task.cancel()
        logger.info("Scheduler: cancelled %s", name)
    _tasks.clear()
