"""Per-user Browserbase settings: store, config resolution, login capture, routes."""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.browser import browserbase_client as bbc
from backend.browser import login_capture
from backend.gateway.routes import browserbase as routes
from backend.shared import browserbase_store as store
from backend.shared.config import settings


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("NEXTAUTH_SECRET", "test-secret-for-browserbase")
    monkeypatch.setattr(settings, "NEXTAUTH_SECRET", "test-secret-for-browserbase")
    monkeypatch.setattr(settings, "BROWSERBASE_CONTEXT_USER_ID", "user-1")
    monkeypatch.setattr(settings, "BROWSERBASE_API_KEY", "bb_env_key")
    monkeypatch.setattr(settings, "BROWSERBASE_PROJECT_ID", "proj-env")
    monkeypatch.setattr(settings, "BROWSERBASE_PROXIES", False)
    monkeypatch.setattr(settings, "BROWSERBASE_SESSION_TIMEOUT", 900)
    monkeypatch.setattr(settings, "BROWSERBASE_CONTEXT_IDS", "indeed=ctx-env-indeed,default=ctx-env-default")
    import backend.shared.credential_store as cs
    cs._fernet = None
    yield
    cs._fernet = None


# ---------------------------------------------------------------------------
# store (fake connection records SQL + params, serves rows)
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, row=None, rowcount=0):
        self._row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self._row


class _FakeConn:
    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []
        self.row = None
        self.rowcount = 0

    def execute(self, sql, params=()):
        self.calls.append((" ".join(sql.split()), params))
        return _FakeCursor(self.row, self.rowcount)

    def commit(self):
        pass


@pytest.fixture
def fake_conn(monkeypatch):
    conn = _FakeConn()

    @contextmanager
    def _get_connection():
        yield conn

    monkeypatch.setattr(store, "get_connection", _get_connection)
    monkeypatch.setattr(store, "_ensured", False)
    return conn


def test_save_encrypts_api_key_and_filters_context_ids(fake_conn):
    store.save_browserbase_settings(
        "user-1", api_key=" bb_live_secret ", project_id=" proj-1 ", proxies=True,
        context_ids={"Indeed": "ctx-a", "linkedin": "ctx-x", "default": "", "glassdoor": " ctx-g "},
    )
    sql, params = next(c for c in fake_conn.calls if c[0].startswith("INSERT INTO browserbase_settings"))
    user_id, encrypted, project, proxies, ctx_json = params
    assert user_id == "user-1"
    assert encrypted and "bb_live_secret" not in encrypted  # Fernet token, not plaintext
    assert project == "proj-1"
    assert proxies is True
    assert json.loads(ctx_json) == {"indeed": "ctx-a", "glassdoor": "ctx-g"}
    assert "encrypted_api_key = EXCLUDED.encrypted_api_key" in sql


def test_save_with_keep_api_key_does_not_touch_stored_key(fake_conn):
    store.save_browserbase_settings(
        "user-1", api_key=None, keep_api_key=True, project_id="p", proxies=False, context_ids={},
    )
    sql, params = next(c for c in fake_conn.calls if c[0].startswith("INSERT INTO browserbase_settings"))
    assert "encrypted_api_key = EXCLUDED" not in sql
    assert params == ("user-1", "p", False, "{}")


def test_get_decrypts_api_key(fake_conn):
    from backend.shared.credential_store import _encrypt
    fake_conn.row = (_encrypt({"api_key": "bb_live_secret"}), "proj-1", True, {"indeed": "ctx-a", "bogus": "x"})
    saved = store.get_browserbase_settings("user-1")
    assert saved == {
        "api_key": "bb_live_secret",
        "project_id": "proj-1",
        "proxies": True,
        "context_ids": {"indeed": "ctx-a"},
    }


def test_get_returns_none_without_row(fake_conn):
    assert store.get_browserbase_settings("user-1") is None


def test_set_context_id_merges_jsonb(fake_conn):
    store.set_context_id("user-1", "Indeed", " ctx-new ")
    sql, params = next(c for c in fake_conn.calls if c[0].startswith("INSERT INTO browserbase_settings"))
    assert "context_ids = browserbase_settings.context_ids || EXCLUDED.context_ids" in sql
    assert params == ("user-1", json.dumps({"indeed": "ctx-new"}))


def test_set_context_id_rejects_unknown_board_and_empty_id(fake_conn):
    with pytest.raises(ValueError):
        store.set_context_id("user-1", "linkedin", "ctx")
    with pytest.raises(ValueError):
        store.set_context_id("user-1", "indeed", "  ")


# ---------------------------------------------------------------------------
# config resolution
# ---------------------------------------------------------------------------


def test_config_from_settings_parses_env():
    cfg = bbc.config_from_settings()
    assert cfg.api_key == "bb_env_key"
    assert cfg.project_id == "proj-env"
    assert cfg.context_ids == {"indeed": "ctx-env-indeed", "default": "ctx-env-default"}
    assert cfg.configured is True
    assert bbc.context_id_for_board("indeed", cfg) == "ctx-env-indeed"


def test_config_for_user_layers_saved_settings_over_env(monkeypatch):
    monkeypatch.setattr(store, "get_browserbase_settings", lambda uid: {
        "api_key": "bb_user_key", "project_id": None, "proxies": True,
        "context_ids": {"indeed": "ctx-user-indeed", "glassdoor": "ctx-user-gd"},
    })
    cfg = bbc.config_for_user("user-1")
    assert cfg.api_key == "bb_user_key"
    assert cfg.project_id == "proj-env"  # user left it blank -> env value
    assert cfg.proxies is True
    assert cfg.context_ids == {
        "indeed": "ctx-user-indeed", "default": "ctx-env-default", "glassdoor": "ctx-user-gd",
    }
    assert cfg.source == "user:user-1"
    assert bbc.context_id_for_board("indeed", cfg) == "ctx-user-indeed"
    assert bbc.context_id_for_board("ziprecruiter", cfg) == "ctx-env-default"


def test_config_for_user_without_saved_settings_or_user_is_env(monkeypatch):
    monkeypatch.setattr(store, "get_browserbase_settings", lambda uid: None)
    assert bbc.config_for_user("user-1").source == "env"
    assert bbc.config_for_user(None).source == "env"
    assert bbc.config_for_user("unknown").source == "env"


@pytest.mark.asyncio
async def test_create_session_uses_explicit_config():
    cfg = bbc.BrowserbaseConfig(api_key="bb_user_key", project_id="proj-user", proxies=True, session_timeout=300)
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    post = MagicMock(status_code=201, text="")
    post.json.return_value = {"id": "sess-u", "connectUrl": "wss://c/u"}
    client.post = AsyncMock(return_value=post)
    dbg = MagicMock(status_code=200)
    dbg.json.return_value = {"debuggerFullscreenUrl": "https://live/u"}
    client.get = AsyncMock(return_value=dbg)

    with patch.object(bbc.httpx, "AsyncClient", return_value=client):
        sess = await bbc.create_session(context_id="ctx-user-indeed", config=cfg)

    body = client.post.await_args.kwargs["json"]
    assert client.post.await_args.kwargs["headers"]["X-BB-API-Key"] == "bb_user_key"
    assert body["projectId"] == "proj-user"
    assert body["proxies"] is True
    assert body["timeout"] == 300
    assert sess.live_view_url == "https://live/u"


# ---------------------------------------------------------------------------
# login capture
# ---------------------------------------------------------------------------


def _fake_playwright(cookie_batches):
    """Playwright stub whose context.cookies() yields *cookie_batches* in order."""
    context = MagicMock()
    context.cookies = AsyncMock(side_effect=list(cookie_batches))
    page = MagicMock()
    page.goto = AsyncMock()
    context.pages = [page]
    browser = MagicMock()
    browser.contexts = [context]
    browser.close = AsyncMock()
    chromium = MagicMock()
    chromium.connect_over_cdp = AsyncMock(return_value=browser)
    pw = MagicMock(chromium=chromium)
    pw.stop = AsyncMock()
    pw_cm = MagicMock()
    pw_cm.start = AsyncMock(return_value=pw)
    return pw_cm, browser, context, page


def _cfg():
    return bbc.BrowserbaseConfig(api_key="bb_user_key", project_id="proj-user", session_timeout=900)


@pytest.mark.asyncio
async def test_login_capture_stores_context_when_login_cookie_appears(monkeypatch):
    pw_cm, browser, context, page = _fake_playwright([
        [],
        [{"name": "CTK", "domain": ".indeed.com"}],
        [{"name": "PPID", "domain": ".indeed.com"}, {"name": "CTK", "domain": ".indeed.com"}],
    ])
    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        if seconds == login_capture.SETTLE_SECONDS:
            assert release.await_count == 1
            assert browser.close.await_count == 1

    create_context = AsyncMock(return_value="ctx-new")
    create_session = AsyncMock(return_value=bbc.BrowserbaseSession(
        id="sess-login", connect_url="wss://c/login", context_id="ctx-new", live_view_url="https://live/login",
    ))
    release = AsyncMock()
    stored: list[tuple] = []

    with patch.object(login_capture, "async_playwright", return_value=pw_cm), \
         patch.object(login_capture.asyncio, "sleep", fake_sleep), \
         patch.object(bbc, "create_context", create_context), \
         patch.object(bbc, "create_session", create_session), \
         patch.object(bbc, "release_session", release):
        registry = login_capture.LoginCaptureRegistry()
        capture = await registry.start(
            user_id="user-1", board="Indeed", config=_cfg(),
            store_context=lambda uid, board, ctx: stored.append((uid, board, ctx)),
        )
        assert capture.status == "waiting"
        assert capture.live_view_url == "https://live/login"
        assert capture.public()["context_id"] is None  # not captured yet
        await asyncio.wait_for(registry._tasks[capture.id], timeout=5)

    create_context.assert_awaited_once()
    assert create_session.await_args.kwargs["context_id"] == "ctx-new"
    assert create_session.await_args.kwargs["persist"] is True
    page.goto.assert_awaited_once()
    assert page.goto.await_args.args[0] == "https://secure.indeed.com/account/login"
    assert context.cookies.await_count == 3
    assert login_capture.SETTLE_SECONDS in sleeps  # allow persisted storage to settle after release
    browser.close.assert_awaited_once()
    release.assert_awaited_once()
    assert release.await_args.args[0] == "sess-login"
    assert stored == [("user-1", "indeed", "ctx-new")]
    assert capture.status == "captured"
    assert capture.public()["context_id"] == "ctx-new"
    assert registry.get(capture.id, "user-1") is capture
    assert registry.get(capture.id, "someone-else") is None


@pytest.mark.asyncio
async def test_login_capture_times_out_without_cookie(monkeypatch):
    pw_cm, browser, context, _ = _fake_playwright([[] for _ in range(50)])
    clock = {"now": 0.0}
    monkeypatch.setattr(login_capture.time, "monotonic", lambda: clock["now"])

    async def fake_sleep(seconds):
        clock["now"] += seconds

    create_session = AsyncMock(return_value=bbc.BrowserbaseSession(
        id="sess-t", connect_url="wss://c/t", context_id="ctx-t", live_view_url=None,
    ))
    release = AsyncMock()
    stored: list = []
    with patch.object(login_capture, "async_playwright", return_value=pw_cm), \
         patch.object(login_capture.asyncio, "sleep", fake_sleep), \
         patch.object(bbc, "create_context", AsyncMock(return_value="ctx-t")), \
         patch.object(bbc, "create_session", create_session), \
         patch.object(bbc, "release_session", release):
        registry = login_capture.LoginCaptureRegistry()
        capture = await registry.start(
            user_id="user-1", board="indeed", config=_cfg(), timeout_seconds=10,
            store_context=lambda *a: stored.append(a),
        )
        await asyncio.wait_for(registry._tasks[capture.id], timeout=5)

    assert capture.status == "timeout"
    assert "PPID cookie did not appear within 10s" in capture.error
    assert stored == []
    browser.close.assert_awaited_once()
    release.assert_awaited_once()


@pytest.mark.asyncio
async def test_login_capture_rejects_unknown_board_and_unconfigured():
    registry = login_capture.LoginCaptureRegistry()
    with pytest.raises(ValueError, match="linkedin"):
        await registry.start(user_id="u", board="linkedin", config=_cfg(), store_context=lambda *a: None)
    with pytest.raises(bbc.BrowserbaseError):
        await registry.start(
            user_id="u", board="indeed", config=bbc.BrowserbaseConfig(), store_context=lambda *a: None,
        )


def test_has_login_cookie_matches_domain_suffix():
    assert login_capture._has_login_cookie([{"name": "PPID", "domain": ".indeed.com"}], "PPID", "indeed.com")
    assert login_capture._has_login_cookie([{"name": "PPID", "domain": "secure.indeed.com"}], "PPID", "indeed.com")
    assert not login_capture._has_login_cookie([{"name": "PPID", "domain": "evil.com"}], "PPID", "indeed.com")
    assert not login_capture._has_login_cookie([{"name": "CTK", "domain": ".indeed.com"}], "PPID", "indeed.com")


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_settings_routes_never_echo_the_api_key(monkeypatch):
    monkeypatch.setattr(routes, "get_current_user", lambda _req: {"id": "user-1"})
    saved = {"api_key": "bb_live_secret_7890", "project_id": "proj-1", "proxies": True,
             "context_ids": {"indeed": "ctx-a"}}
    monkeypatch.setattr(store, "get_browserbase_settings", lambda uid: saved)

    body = await routes.get_settings_route(MagicMock())
    assert body["api_key_set"] is True
    assert body["api_key_hint"] == "…7890"
    assert "bb_live_secret" not in json.dumps(body)
    assert body["context_ids"] == {"indeed": "ctx-a"}
    assert body["effective_configured"] is True
    assert "indeed" in body["login_capture_boards"]


@pytest.mark.asyncio
async def test_put_settings_keeps_key_when_omitted_and_rejects_unknown_boards(monkeypatch):
    monkeypatch.setattr(routes, "get_current_user", lambda _req: {"id": "user-1"})
    save = MagicMock(return_value={})
    monkeypatch.setattr(store, "save_browserbase_settings", save)
    monkeypatch.setattr(store, "get_browserbase_settings", lambda uid: None)

    await routes.update_settings_route(MagicMock(), routes.BrowserbaseSettingsUpdate(
        project_id="proj-1", proxies=True, context_ids={"indeed": "ctx-a"},
    ))
    assert save.call_args.kwargs["keep_api_key"] is True
    assert save.call_args.kwargs["api_key"] is None

    await routes.update_settings_route(MagicMock(), routes.BrowserbaseSettingsUpdate(
        api_key="bb_new", project_id="proj-1", proxies=False, context_ids={},
    ))
    assert save.call_args.kwargs["keep_api_key"] is False
    assert save.call_args.kwargs["api_key"] == "bb_new"

    response = await routes.update_settings_route(MagicMock(), routes.BrowserbaseSettingsUpdate(
        context_ids={"linkedin": "ctx-x"},
    ))
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_start_login_session_requires_config_and_known_board(monkeypatch):
    monkeypatch.setattr(routes, "get_current_user", lambda _req: {"id": "user-1"})
    monkeypatch.setattr(bbc, "config_for_user", lambda uid: bbc.BrowserbaseConfig())

    response = await routes.start_login_session(MagicMock(), routes.LoginSessionStart(board="indeed"))
    assert response.status_code == 400

    response = await routes.start_login_session(MagicMock(), routes.LoginSessionStart(board="linkedin"))
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_start_and_poll_login_session(monkeypatch):
    monkeypatch.setattr(routes, "get_current_user", lambda _req: {"id": "user-1"})
    monkeypatch.setattr(bbc, "config_for_user", lambda uid: _cfg())
    capture = login_capture.LoginCapture(
        id="cap-1", user_id="user-1", board="indeed", context_id="ctx-new",
        browserbase_session_id="sess-1", live_view_url="https://live/1",
    )
    start = AsyncMock(return_value=capture)
    monkeypatch.setattr(login_capture.registry, "start", start)
    monkeypatch.setattr(login_capture.registry, "get",
                        lambda cid, uid: capture if (cid, uid) == ("cap-1", "user-1") else None)

    started = await routes.start_login_session(MagicMock(), routes.LoginSessionStart(board="Indeed"))
    assert started["capture_id"] == "cap-1"
    assert started["live_view_url"] == "https://live/1"
    assert started["status"] == "waiting"
    assert start.await_args.kwargs["store_context"] is store.set_context_id
    assert start.await_args.kwargs["board"] == "indeed"

    polled = await routes.get_login_session(MagicMock(), "cap-1")
    assert polled["status"] == "waiting"
    missing = await routes.get_login_session(MagicMock(), "nope")
    assert missing.status_code == 404


def test_login_cookie_rejects_lookalike_domain():
    assert not login_capture._has_login_cookie([{'name': 'PPID', 'domain': 'evilindeed.com'}], 'PPID', 'indeed.com')


def test_server_context_is_not_shared_with_other_accounts(monkeypatch):
    monkeypatch.setattr(store, 'get_browserbase_settings', lambda uid: None)
    assert bbc.config_for_user('another-user').context_ids == {}
    assert bbc.config_for_user(None).context_ids == {}


@pytest.mark.parametrize('uid', [None, 'unknown', 'another-user'])
def test_other_accounts_never_inherit_server_credentials(monkeypatch, uid):
    monkeypatch.setattr(store, 'get_browserbase_settings', lambda _: None)
    config = bbc.config_for_user(uid)
    assert not config.configured
    assert config.api_key is None and config.project_id is None
    assert config.context_ids == {}


@pytest.mark.parametrize('overrides', [
    {'project_id': 'proj-env'},
    {'api_key': 'bb_env_key'},
    {'context_ids': {'indeed': 'ctx-env-indeed'}},
])
def test_public_account_cannot_claim_server_project_or_context(monkeypatch, overrides):
    saved = {'api_key': 'own-key', 'project_id': 'own-project', 'context_ids': {'indeed': 'own-context'}}
    saved.update(overrides)
    monkeypatch.setattr(store, 'get_browserbase_settings', lambda _: saved)
    config = bbc.config_for_user('another-user')
    assert not config.configured
    assert config.context_ids == {}


def test_public_account_can_only_use_its_complete_own_configuration(monkeypatch):
    monkeypatch.setattr(store, 'get_browserbase_settings', lambda _: {
        'api_key': 'own-key', 'project_id': 'own-project', 'context_ids': {'indeed': 'own-context'},
    })
    config = bbc.config_for_user('another-user')
    assert config.configured
    assert config.api_key == 'own-key' and config.project_id == 'own-project'
    assert config.context_ids == {'indeed': 'own-context'}
