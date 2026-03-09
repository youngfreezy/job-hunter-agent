# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Shared synchronous connection pool for all store modules.

Instead of creating a new TCP connection per query, all store files
should use `get_pool().connection()` to check out a reusable connection.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg_pool import ConnectionPool

from backend.shared.config import get_settings

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    """Return the shared sync connection pool (lazy-initialized)."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=get_settings().DATABASE_URL,
            min_size=2,
            max_size=10,
            open=True,
        )
        logger.info("Sync connection pool opened (min=2, max=10)")
    return _pool


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    """Check out a pooled connection (context manager).

    Usage:
        with get_connection() as conn:
            conn.execute(...)
            conn.commit()

    On exit the connection is returned to the pool (not destroyed).
    """
    with get_pool().connection() as conn:
        yield conn


def close_pool() -> None:
    """Close the pool during application shutdown."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
        logger.info("Sync connection pool closed")
