"""Browserbase cloud-browser mode: client, board-to-Context mapping, manager lifecycle."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.browser import browserbase_client as bbc
from backend.browser.manager import BrowserManager
from backend.shared.config import settings
from backend.shared.models.schemas import JobBoard


@pytest.fixture(autouse=True)
def _bb_settings(monkeypatch):
    monkeypatch.setattr(settings, "BROWSERBASE_CONTEXT_USER_ID", "owner")
    monkeypatch.setattr("backend.shared.browserbase_store.get_browserbase_settings", lambda uid: None)
    monkeypatch.setattr(settings, "BROWSERBASE_API_KEY", "bb_live_test")
    monkeypatch.setattr(settings, "BROWSERBASE_PROJECT_ID", "proj-123")
    monkeypatch.setattr(settings, "BROWSERBASE_PROXIES", False)
    monkeypatch.setattr(settings, "BROWSERBASE_SESSION_TIMEOUT", 600)
    monkeypatch.setattr(settings, "BROWSERBASE_CONTEXT_IDS", "indeed=ctx-indeed, default=ctx-default")
    monkeypatch.setattr(settings, "BROWSERBASE_BLOCK_MEDIA", True)


def test_context_id_for_board_resolves_board_then_default():
    assert bbc.context_id_for_board("indeed") == "ctx-indeed"
    assert bbc.context_id_for_board(JobBoard.INDEED) == "ctx-indeed"
    assert bbc.context_id_for_board("linkedin") == "ctx-default"
    assert bbc.context_id_for_board(None) == "ctx-default"


def test_context_id_for_board_empty_setting(monkeypatch):
    monkeypatch.setattr(settings, "BROWSERBASE_CONTEXT_IDS", "")
    assert bbc.context_id_for_board("indeed") is None


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def _fake_client(post_payload, debug_payload):
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(return_value=_FakeResponse(201, post_payload))
    client.get = AsyncMock(return_value=_FakeResponse(200, debug_payload))
    return client


@pytest.mark.asyncio
async def test_create_session_binds_context_and_fetches_live_view():
    client = _fake_client(
        {"id": "sess-1", "connectUrl": "wss://connect.browserbase.com/x"},
        {"debuggerFullscreenUrl": "https://www.browserbase.com/devtools-fullscreen/1"},
    )
    with patch.object(bbc.httpx, "AsyncClient", return_value=client):
        sess = await bbc.create_session(context_id="ctx-indeed", persist=True)

    assert sess.id == "sess-1"
    assert sess.connect_url.startswith("wss://")
    assert sess.live_view_url.endswith("/1")
    body = client.post.await_args.kwargs["json"]
    assert body["projectId"] == "proj-123"
    assert body["browserSettings"]["context"] == {"id": "ctx-indeed", "persist": True}
    assert body["timeout"] == 600
    assert "proxies" not in body


@pytest.mark.asyncio
async def test_create_session_raises_on_api_error():
    client = _fake_client({"error": "nope"}, {})
    client.post = AsyncMock(return_value=_FakeResponse(401, {"error": "Unauthorized"}))
    with patch.object(bbc.httpx, "AsyncClient", return_value=client):
        with pytest.raises(bbc.BrowserbaseError):
            await bbc.create_session()


@pytest.mark.asyncio
async def test_manager_start_for_task_uses_browserbase_and_releases_on_stop(monkeypatch):
    monkeypatch.setattr(settings, "BROWSER_MODE", "browserbase")

    fake_session = bbc.BrowserbaseSession(
        id="sess-9", connect_url="wss://connect/9", context_id="ctx-indeed",
        live_view_url="https://live/9",
    )
    create = AsyncMock(return_value=fake_session)
    release = AsyncMock()

    fake_context = MagicMock()
    fake_context.route = AsyncMock()
    fake_browser = MagicMock()
    fake_browser.contexts = [fake_context]
    fake_browser.close = AsyncMock()
    fake_chromium = MagicMock()
    fake_chromium.connect_over_cdp = AsyncMock(return_value=fake_browser)
    fake_pw = MagicMock()
    fake_pw.chromium = fake_chromium
    fake_pw.stop = AsyncMock()
    fake_pw_cm = MagicMock()
    fake_pw_cm.start = AsyncMock(return_value=fake_pw)

    with patch.object(bbc, "create_session", create), \
         patch.object(bbc, "release_session", release), \
         patch("backend.browser.manager.cloud_async_playwright", return_value=fake_pw_cm):
        mgr = BrowserManager()
        await mgr.start_for_task(board=JobBoard.INDEED, purpose="apply", user_id="owner")

        assert mgr.mode == "browserbase"
        assert mgr.browserbase_session_id == "sess-9"
        assert mgr.live_view_url == "https://live/9"
        create.assert_awaited_once()
        assert create.await_args.kwargs["context_id"] == "ctx-indeed"
        fake_chromium.connect_over_cdp.assert_awaited_once()
        assert fake_chromium.connect_over_cdp.await_args.args[0] == "wss://connect/9"

        ctx_id, ctx = await mgr.new_context()
        assert ctx is fake_context
        fake_context.route.assert_awaited_once()  # media blocking installed

        await mgr.stop()
        release.assert_awaited_once()
        assert release.await_args.args[0] == "sess-9"
        assert release.await_args.kwargs["config"].api_key == "bb_live_test"
        assert mgr.browserbase_session_id is None


@pytest.mark.asyncio
async def test_manager_releases_session_if_cdp_connect_fails():
    fake_session = bbc.BrowserbaseSession(id="sess-x", connect_url="wss://c/x", context_id=None)
    release = AsyncMock()
    fake_chromium = MagicMock()
    fake_chromium.connect_over_cdp = AsyncMock(side_effect=RuntimeError("boom"))
    fake_pw = MagicMock(chromium=fake_chromium)
    fake_pw.stop = AsyncMock()
    fake_pw_cm = MagicMock()
    fake_pw_cm.start = AsyncMock(return_value=fake_pw)

    with patch.object(bbc, "create_session", AsyncMock(return_value=fake_session)), \
         patch.object(bbc, "release_session", release), \
         patch("backend.browser.manager.cloud_async_playwright", return_value=fake_pw_cm):
        mgr = BrowserManager()
        with pytest.raises(RuntimeError):
            await mgr.start_browserbase()
        release.assert_awaited_once()
        assert release.await_args.args[0] == "sess-x"
        assert mgr.browserbase_session_id is None


@pytest.mark.asyncio
async def test_cloud_manager_uses_standard_playwright_without_local_driver(monkeypatch):
    import backend.browser.manager as module
    session = bbc.BrowserbaseSession(id='cloud', connect_url='wss://cloud.test', context_id=None)
    browser = MagicMock()
    browser.close = AsyncMock()
    driver = MagicMock()
    driver.chromium.connect_over_cdp = AsyncMock(return_value=browser)
    driver.stop = AsyncMock()
    factory = MagicMock()
    factory.start = AsyncMock(return_value=driver)
    monkeypatch.setattr(module, 'cloud_async_playwright', lambda: factory, raising=False)
    monkeypatch.setattr(module, 'async_playwright', MagicMock(side_effect=AssertionError('Local driver used for Browserbase')))
    monkeypatch.setattr(bbc, 'create_session', AsyncMock(return_value=session))
    monkeypatch.setattr(bbc, 'release_session', AsyncMock())
    manager = BrowserManager()
    await manager.start_browserbase()
    assert manager.mode == 'browserbase'
    await manager.stop()
    driver.chromium.connect_over_cdp.assert_awaited_once_with('wss://cloud.test', timeout=45_000)
    driver.stop.assert_awaited_once()
