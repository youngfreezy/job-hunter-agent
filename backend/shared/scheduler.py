# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Lightweight async periodic scheduler with optional LISTEN/NOTIFY support.

Usage during app startup::

    from backend.shared.scheduler import schedule, schedule_seconds, schedule_with_notify, cancel_all
    schedule("selector-health-check", run_health_check, interval_hours=24.0)
    schedule_with_notify("autopilot-checker", check_autopilot,
                         channel="autopilot_schedules_changed",
                         fallback_interval_seconds=300)
    # on shutdown:
    cancel_all()
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_tasks: dict[str, asyncio.Task] = {}


async def _run_periodic(name: str, coro_factory, interval_seconds: float, *, run_immediately: bool = False):
    """Run *coro_factory()* every *interval_seconds*."""
    first = True
    while True:
        try:
            if first and run_immediately:
                first = False
                # Small delay to let startup complete
                await asyncio.sleep(10)
            else:
                first = False
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


def schedule_seconds(name: str, coro_factory, interval_seconds: float = 60.0, *, run_immediately: bool = False):
    """Register a periodic task (seconds). Call during app startup."""
    if name in _tasks:
        logger.warning("Scheduler: %s already registered, skipping", name)
        return
    task = asyncio.create_task(_run_periodic(name, coro_factory, interval_seconds, run_immediately=run_immediately))
    _tasks[name] = task
    logger.info("Scheduler: registered %s (every %.0fs)", name, interval_seconds)


async def _run_listen_notify(
    name: str,
    coro_factory,
    channel: str,
    fallback_interval_seconds: float,
    database_url: str,
):
    """Listen for PG notifications on *channel*, running *coro_factory()* on each.

    Also runs *coro_factory()* every *fallback_interval_seconds* to catch
    schedules that become due purely by clock advancement (no INSERT/UPDATE).
    Reconnects automatically on connection loss.
    """
    from psycopg import AsyncConnection, OperationalError

    while True:
        conn = None
        try:
            conn = await AsyncConnection.connect(database_url, autocommit=True)
            await conn.execute(f"LISTEN {channel}")
            logger.info("Scheduler: %s listening on channel %s", name, channel)

            # Run once immediately on connect to catch anything due now
            await coro_factory()

            while True:
                # notifies() exits the loop on timeout — we re-enter to keep listening
                async for notify in conn.notifies(timeout=fallback_interval_seconds):
                    logger.info("Scheduler: %s triggered by NOTIFY (payload=%s)", name, notify.payload)
                    await coro_factory()
                    logger.info("Scheduler: %s completed", name)

                # Timeout reached — fallback poll for clock-based due schedules
                logger.info("Scheduler: running %s (fallback poll)", name)
                await coro_factory()
                logger.info("Scheduler: %s completed", name)

        except asyncio.CancelledError:
            break
        except OperationalError:
            logger.warning("Scheduler: %s lost DB connection, reconnecting in 5s", name)
            await asyncio.sleep(5)
        except Exception:
            logger.exception("Scheduler: %s failed, retrying in 10s", name)
            await asyncio.sleep(10)
        finally:
            if conn is not None:
                try:
                    await conn.close()
                except Exception:
                    pass


def schedule_with_notify(
    name: str,
    coro_factory,
    *,
    channel: str,
    fallback_interval_seconds: float = 300.0,
    database_url: str | None = None,
):
    """Register a task driven by PG LISTEN/NOTIFY with a fallback poll.

    Requires a PG trigger that sends NOTIFY on the given channel.
    """
    if name in _tasks:
        logger.warning("Scheduler: %s already registered, skipping", name)
        return
    if database_url is None:
        from backend.shared.config import get_settings
        database_url = get_settings().DATABASE_URL
    task = asyncio.create_task(
        _run_listen_notify(name, coro_factory, channel, fallback_interval_seconds, database_url)
    )
    _tasks[name] = task
    logger.info(
        "Scheduler: registered %s (LISTEN %s, fallback every %.0fs)",
        name, channel, fallback_interval_seconds,
    )


def cancel_all():
    """Cancel all scheduled tasks. Call during app shutdown."""
    for name, task in _tasks.items():
        task.cancel()
        logger.info("Scheduler: cancelled %s", name)
    _tasks.clear()
