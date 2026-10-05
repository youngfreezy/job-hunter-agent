"""Cancellation during cloud startup must release the paid Browserbase session."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.browser import browserbase_client as bbc
from backend.browser.manager import BrowserManager


@pytest.mark.asyncio
async def test_cancelled_browser_connect_releases_cloud_session_and_driver(monkeypatch):
    session = bbc.BrowserbaseSession("cancelled-session", "wss://fixture.invalid", None)
    release = AsyncMock()
    driver = SimpleNamespace(
        chromium=SimpleNamespace(connect_over_cdp=AsyncMock(side_effect=asyncio.CancelledError)),
        stop=AsyncMock(),
    )
    monkeypatch.setattr(bbc, "create_session", AsyncMock(return_value=session))
    monkeypatch.setattr(bbc, "release_session", release)
    monkeypatch.setattr("backend.browser.manager.cloud_async_playwright",
                        lambda: SimpleNamespace(start=AsyncMock(return_value=driver)))

    manager = BrowserManager()
    with pytest.raises(asyncio.CancelledError):
        await manager.start_browserbase()

    release.assert_awaited_once_with("cancelled-session", config=None)
    driver.stop.assert_awaited_once()
    assert manager.browserbase_session_id is None
