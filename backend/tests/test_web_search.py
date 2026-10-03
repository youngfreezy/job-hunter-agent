"""Web search backends for discovery: selection, the Browserbase request shape, paging."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.browser.tools import mcp_discovery
from backend.browser.tools import web_search as ws
from backend.shared.config import settings


def _client(response):
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(return_value=response)
    return client


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise ws.httpx.HTTPStatusError("boom", request=MagicMock(), response=MagicMock(status_code=self.status_code))

    def json(self):
        return self._payload


# ---------------------------------------------------------------------------
# backend selection
# ---------------------------------------------------------------------------


def test_serper_wins_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "SERPER_API_KEY", "serper-key")
    monkeypatch.setattr(settings, "BROWSERBASE_API_KEY", "bb_live_x")
    assert ws.search_backend() == "serper"


def test_browserbase_is_used_without_serper(monkeypatch):
    monkeypatch.setattr(settings, "SERPER_API_KEY", None)
    monkeypatch.setattr(settings, "BROWSERBASE_API_KEY", "bb_live_x")
    assert ws.search_backend() == "browserbase"


def test_no_backend_without_keys(monkeypatch):
    monkeypatch.setattr(settings, "SERPER_API_KEY", None)
    monkeypatch.setattr(settings, "BROWSERBASE_API_KEY", None)
    assert ws.search_backend() is None


@pytest.mark.asyncio
async def test_web_search_raises_without_backend(monkeypatch):
    monkeypatch.setattr(settings, "SERPER_API_KEY", None)
    monkeypatch.setattr(settings, "BROWSERBASE_API_KEY", None)
    with pytest.raises(RuntimeError, match="No web search backend"):
        await ws.web_search("ai engineer")


@pytest.mark.asyncio
async def test_web_search_delegates_to_serper_with_its_options(monkeypatch):
    monkeypatch.setattr(settings, "SERPER_API_KEY", "serper-key")
    serper = AsyncMock(return_value='{"organic": []}')
    monkeypatch.setattr(ws, "serper_search", serper)
    out = await ws.web_search("q", num_results=20, tbs="qdr:m", page=2)
    serper.assert_awaited_once_with("q", num_results=20, tbs="qdr:m", page=2)
    assert out == '{"organic": []}'


# ---------------------------------------------------------------------------
# browserbase_search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_browserbase_search_posts_documented_body_and_normalises(monkeypatch):
    monkeypatch.setattr(settings, "SERPER_API_KEY", None)
    monkeypatch.setattr(settings, "BROWSERBASE_API_KEY", "bb_live_x")
    payload = {
        "requestId": "req_1",
        "query": "applied ai engineer site:jobs.lever.co",
        "results": [
            {"id": "a", "url": "https://jobs.lever.co/acme/1", "title": "Acme - Applied AI Engineer",
             "publishedDate": "2026-09-30T00:00:00Z"},
            {"id": "b", "url": "https://jobs.ashbyhq.com/beta/2", "title": "AI Engineer @ Beta"},
            {"id": "c", "title": "no url, dropped"},
        ],
    }
    client = _client(_Resp(payload))
    with patch.object(ws.httpx, "AsyncClient", return_value=client):
        out = await ws.web_search("applied ai engineer site:jobs.lever.co", num_results=20)

    args, kwargs = client.post.await_args
    assert args[0] == "https://api.browserbase.com/v1/search"
    assert kwargs["headers"]["X-BB-API-Key"] == "bb_live_x"
    assert kwargs["json"] == {"query": "applied ai engineer site:jobs.lever.co", "numResults": 20}

    organic = json.loads(out)["organic"]
    assert organic == [
        {"title": "Acme - Applied AI Engineer", "link": "https://jobs.lever.co/acme/1",
         "description": "Published 2026-09-30T00:00:00Z"},
        {"title": "AI Engineer @ Beta", "link": "https://jobs.ashbyhq.com/beta/2", "description": ""},
    ]


@pytest.mark.asyncio
async def test_browserbase_search_clamps_num_results_and_query_length(monkeypatch):
    monkeypatch.setattr(settings, "SERPER_API_KEY", None)
    monkeypatch.setattr(settings, "BROWSERBASE_API_KEY", "bb_live_x")
    client = _client(_Resp({"requestId": "r", "query": "q", "results": []}))
    with patch.object(ws.httpx, "AsyncClient", return_value=client):
        await ws.browserbase_search("x" * 500, num_results=100)
    body = client.post.await_args.kwargs["json"]
    assert body["numResults"] == 25
    assert len(body["query"]) == 200


@pytest.mark.asyncio
async def test_browserbase_search_has_no_second_page(monkeypatch):
    monkeypatch.setattr(settings, "SERPER_API_KEY", None)
    monkeypatch.setattr(settings, "BROWSERBASE_API_KEY", "bb_live_x")
    client = _client(_Resp({"requestId": "r", "query": "q", "results": []}))
    with patch.object(ws.httpx, "AsyncClient", return_value=client):
        assert await ws.web_search("q", page=2) is None
    client.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_browserbase_search_raises_on_http_error_and_bad_shape(monkeypatch):
    monkeypatch.setattr(settings, "SERPER_API_KEY", None)
    monkeypatch.setattr(settings, "BROWSERBASE_API_KEY", "bb_live_x")
    with patch.object(ws.httpx, "AsyncClient", return_value=_client(_Resp({"error": "x"}, status_code=401))):
        with pytest.raises(ws.httpx.HTTPStatusError):
            await ws.browserbase_search("q")
    with patch.object(ws.httpx, "AsyncClient", return_value=_client(_Resp({"requestId": "r"}))):
        with pytest.raises(RuntimeError, match="no results list"):
            await ws.browserbase_search("q")


# ---------------------------------------------------------------------------
# discovery uses the shared backend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_discovery_builds_listings_from_browserbase_results(monkeypatch):
    monkeypatch.setattr(settings, "SERPER_API_KEY", None)
    monkeypatch.setattr(settings, "BROWSERBASE_API_KEY", "bb_live_x")
    monkeypatch.setattr(mcp_discovery, "emit_agent_event", AsyncMock())
    monkeypatch.setattr(mcp_discovery, "_generate_search_queries", AsyncMock(return_value=["q1", "q2"]))

    seen: list = []

    async def fake_web_search(query, num_results=20, tbs="qdr:w", page=1):
        seen.append((query, page))
        if page > 1:
            return None
        return json.dumps({"organic": [
            {"title": "Acme - Applied AI Engineer", "link": "https://jobs.lever.co/acme/1", "description": ""},
        ]})

    monkeypatch.setattr(mcp_discovery, "web_search", fake_web_search)
    monkeypatch.setattr(mcp_discovery, "_parse_search_results", AsyncMock(return_value=[
        {"title": "Applied AI Engineer", "company": "Acme", "url": "https://jobs.lever.co/acme/1",
         "location": "San Francisco, CA"},
    ]))

    from backend.shared.models.schemas import SearchConfig
    listings = await mcp_discovery._mcp_discover(
        SearchConfig(keywords=["applied AI engineer"], locations=["San Francisco, CA"]), "s1", max_results=20,
    )

    assert [l.url for l in listings] == ["https://jobs.lever.co/acme/1"]
    assert listings[0].company == "Acme" and listings[0].location == "San Francisco, CA"
    # Page 1 for both queries, then the page-2 deepening (which Browserbase declines) for both.
    assert seen == [("q1", 1), ("q2", 1), ("q1", 2), ("q2", 2)]


@pytest.mark.asyncio
async def test_search_discovery_skips_cleanly_without_a_backend(monkeypatch):
    monkeypatch.setattr(settings, "SERPER_API_KEY", None)
    monkeypatch.setattr(settings, "BROWSERBASE_API_KEY", None)
    events: list = []

    async def fake_emit(_sid, event, payload):
        events.append((event, payload))

    monkeypatch.setattr(mcp_discovery, "emit_agent_event", fake_emit)
    generate = AsyncMock()
    monkeypatch.setattr(mcp_discovery, "_generate_search_queries", generate)

    from backend.shared.models.schemas import SearchConfig
    listings = await mcp_discovery._mcp_discover(SearchConfig(keywords=["x"], locations=["y"]), "s1")

    assert listings == []
    generate.assert_not_awaited()  # no LLM call when nothing could run the queries
    assert any(p.get("error") for _, p in events)
