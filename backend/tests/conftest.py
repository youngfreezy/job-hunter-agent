"""Shared pytest configuration for backend unit tests.

Most tests run fully in-process with mocks.  A few exercise the real Postgres
store modules (resume persistence, double-submit prevention).  Those are marked
``requires_postgres``; when no server answers at ``settings.DATABASE_URL`` they
are skipped with an explicit reason instead of hanging on the pool's 30 second
connect timeout and erroring out.
"""

from __future__ import annotations

import functools

import psycopg
import pytest

from backend.shared.config import get_settings, settings


@pytest.fixture(autouse=True)
def _no_live_browserbase(monkeypatch):
    """Keep every test off the live Browserbase API.

    Settings read the repo's ``.env``; with a real ``BROWSERBASE_API_KEY`` in
    it the listing verifier would fetch the test fixtures' fake job URLs for
    real (and spend quota) inside tests that never meant to touch the network.
    Tests that exercise Browserbase code set the values they need themselves.
    """
    monkeypatch.setattr(settings, "BROWSERBASE_API_KEY", None)
    monkeypatch.setattr(settings, "BROWSERBASE_PROJECT_ID", None)
    monkeypatch.setattr(settings, "BROWSERBASE_CONTEXT_IDS", "")
    monkeypatch.setattr(settings, "BROWSERBASE_PROXIES", False)
    monkeypatch.setattr(settings, "BROWSERBASE_VERIFY_LISTINGS", False)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_postgres: test needs a live Postgres at settings.DATABASE_URL",
    )


@functools.lru_cache(maxsize=1)
def _postgres_unavailable_reason() -> str | None:
    """Return None when Postgres is reachable, else a human-readable reason."""
    url = get_settings().DATABASE_URL
    try:
        with psycopg.connect(url, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
    except psycopg.Error as exc:  # connection refused, auth failure, ...
        first_line = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
        return f"Postgres not reachable at DATABASE_URL ({first_line})"
    return None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    db_items = [item for item in items if item.get_closest_marker("requires_postgres")]
    if not db_items:
        return
    reason = _postgres_unavailable_reason()
    if reason is None:
        return
    skip = pytest.mark.skip(reason=reason)
    for item in db_items:
        item.add_marker(skip)
