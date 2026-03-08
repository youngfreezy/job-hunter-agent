# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Lightweight async periodic scheduler — no external deps.

Usage during app startup::

    from backend.shared.scheduler import schedule, schedule_seconds, cancel_all
    schedule("selector-health-check", run_health_check, interval_hours=24.0)
    schedule_seconds("autopilot-checker", check_autopilot, interval_seconds=60)
    # on shutdown:
    cancel_all()
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_tasks: dict[str, asyncio.Task] = {}


async def _run_periodic(name: str, coro_factory, interval_seconds: float):
    """Run *coro_factory()* every *interval_seconds*."""
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            logger.info("Scheduler: running %s", name)
            await coro_factory()
            logger.info("Scheduler: %s completed", name)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Scheduler: %s failed", name)


def schedule(name: str, coro_factory, interval_hours: float = 24.0):
    """Register a periodic task (hours). Call during app startup."""
    if name in _tasks:
        logger.warning("Scheduler: %s already registered, skipping", name)
        return
    task = asyncio.create_task(_run_periodic(name, coro_factory, interval_hours * 3600))
    _tasks[name] = task
    logger.info("Scheduler: registered %s (every %.1fh)", name, interval_hours)


def schedule_seconds(name: str, coro_factory, interval_seconds: float = 60.0):
    """Register a periodic task (seconds). Call during app startup."""
    if name in _tasks:
        logger.warning("Scheduler: %s already registered, skipping", name)
        return
    task = asyncio.create_task(_run_periodic(name, coro_factory, interval_seconds))
    _tasks[name] = task
    logger.info("Scheduler: registered %s (every %.0fs)", name, interval_seconds)


def cancel_all():
    """Cancel all scheduled tasks. Call during app shutdown."""
    for name, task in _tasks.items():
        task.cancel()
        logger.info("Scheduler: cancelled %s", name)
    _tasks.clear()
