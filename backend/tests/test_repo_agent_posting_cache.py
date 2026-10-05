"""Public posting caches must refresh without a server restart."""

from unittest.mock import AsyncMock

import httpx
import pytest

from backend.browser.tools import ats_posting_api as api


@pytest.fixture(autouse=True)
def empty_board_cache():
    api._ashby_board_cache.clear()
    yield
    api._ashby_board_cache.clear()


def response(status, payload):
    return httpx.Response(status, json=payload, request=httpx.Request("GET", "https://api.ashbyhq.com"))


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_status, initial", [(200, {"jobs": []}), (404, None)])
async def test_posting_cache_refreshes_stale_success_and_missing_board(monkeypatch, initial_status, initial):
    now = [0.0]
    monkeypatch.setattr("time.monotonic", lambda: now[0])
    current = {"jobs": [{"id": "newly-opened"}]}
    client = AsyncMock()
    client.get.side_effect = [response(initial_status, initial), response(200, current)]

    assert await api._ashby_board("acme", client) == initial
    now[0] = 301.0
    assert await api._ashby_board("acme", client) == current
    assert client.get.await_count == 2


@pytest.mark.asyncio
async def test_posting_cache_keeps_recent_boards_and_evicts_oldest():
    client = AsyncMock()
    client.get.return_value = response(200, {"jobs": []})
    for index in range(129):
        await api._ashby_board(f"org-{index}", client)
    assert len(api._ashby_board_cache) == 128
    await api._ashby_board("org-128", client)
    assert client.get.await_count == 129
    await api._ashby_board("org-0", client)
    assert client.get.await_count == 130
