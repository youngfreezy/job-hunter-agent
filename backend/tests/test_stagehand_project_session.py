"""Offline provider-transport and cleanup contracts for project-bound sessions."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from browserbase import AsyncBrowserbase as RealBrowserbase

from backend.browser import stagehand_session as subject
from backend.browser.browserbase_client import BrowserbaseConfig
from backend.shared.config import settings


@pytest.fixture
def transport(monkeypatch):
    requests, events = [], []
    state = {'project': 'visitor-project', 'fail': None}
    monkeypatch.setattr(settings, 'BACKEND_PUBLIC_URL', 'https://api.jobhunteragent.com')
    real_http = httpx.AsyncClient

    def respond(request):
        requests.append(request)
        if request.method == 'POST' and request.url.path == '/v1/extensions':
            events.append('upload')
            return httpx.Response(200, json={'id': 'uploaded-extension'})
        if request.method == 'POST' and request.url.path == '/v1/sessions':
            events.append('create')
            if state['fail'] == 'create':
                return httpx.Response(400, json={'message': 'offline failure'})
            return httpx.Response(200, json={'id': 'session-one', 'projectId': state['project'], 'connectUrl': 'wss://offline'})
        if request.method == 'POST' and request.url.path == '/v1/sessions/session-one':
            events.append('release')
            if state['fail'] == 'release':
                return httpx.Response(400, json={'message': 'offline release failure'})
            return httpx.Response(200, json={'id': 'session-one'})
        if request.method == 'DELETE':
            events.append('delete-extension')
            return httpx.Response(204)
        if request.url.path.endswith('/debug'):
            return httpx.Response(200, json={'debuggerUrl': 'https://offline'})
        return httpx.Response(200, json={'projectId': state['project'], 'connectUrl': 'wss://offline'})

    wire = httpx.MockTransport(respond)
    monkeypatch.setattr(subject, 'AsyncBrowserbase', lambda **kw: RealBrowserbase(**kw, http_client=real_http(transport=wire)))
    monkeypatch.setattr(subject, 'httpx', SimpleNamespace(AsyncClient=lambda **kw: real_http(**kw, transport=wire)))
    monkeypatch.setattr(subject, 'current_model_credentials', lambda: SimpleNamespace(api_key='fictional-model-key'))
    monkeypatch.setattr(subject, 'current_model_user', lambda: 'visitor')
    monkeypatch.setattr(subject, 'build_extension_archive', lambda: b'offline-extension-archive')

    async def close_browser():
        events.append('browser-close')
        if state['fail'] == 'browser-close':
            raise RuntimeError('offline disconnect failure')

    browser = SimpleNamespace(session_id='session-one', close=close_browser)
    connect = AsyncMock(return_value=browser)
    monkeypatch.setattr(subject.browserbase, 'connect', connect)
    monkeypatch.setattr(subject.browserbase, 'launch', AsyncMock(side_effect=AssertionError('launch loses project')))
    async def close_agent(): events.append('agent-close')
    agent = SimpleNamespace(close=close_agent)
    create = AsyncMock(return_value=agent)
    monkeypatch.setattr(subject.Stagehand, 'create', create)
    return SimpleNamespace(requests=requests, events=events, state=state, connect=connect, create=create)


async def launch():
    return await subject.launch_stagehand(BrowserbaseConfig(api_key='fictional-browser-key', project_id='visitor-project', proxies=True, session_timeout=900), 'visitor-context')


@pytest.mark.asyncio
async def test_installed_sdk_serializes_project_extension_context_and_lifetime(transport):
    _, info, cleanup = await launch()
    request = next(r for r in transport.requests if r.url.path == '/v1/sessions' and r.method == 'POST')
    payload = json.loads(request.content)
    assert payload['projectId'] == 'visitor-project'
    assert payload['extensionId'] == 'uploaded-extension'
    assert payload['browserSettings'] == {'context': {'id': 'visitor-context', 'persist': True}, 'solveCaptchas': True}
    assert payload['timeout'] == 900 and payload['proxies'] is True
    assert info.id == 'session-one'
    transport.connect.assert_awaited_once_with(api_key='fictional-browser-key', session_id='session-one')
    await cleanup.aclose()
    assert transport.events == ['upload', 'create', 'agent-close', 'browser-close', 'release', 'delete-extension']
    release = next(r for r in transport.requests if r.url.path.endswith('/session-one') and r.method == 'POST')
    assert json.loads(release.content) == {'status': 'REQUEST_RELEASE', 'projectId': 'visitor-project'}


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['create', 'project', 'connect', 'agent', 'browser-close', 'release'])
async def test_owned_resources_clean_up_on_every_failure(transport, failure):
    transport.state['fail'] = failure
    if failure == 'project': transport.state['project'] = 'wrong-project'
    if failure == 'connect': transport.connect.side_effect = RuntimeError('offline connect failure')
    if failure == 'agent': transport.create.side_effect = RuntimeError('offline agent failure')
    with pytest.raises(Exception):
        _, _, cleanup = await launch()
        await cleanup.aclose()
    assert transport.events[-1] == 'delete-extension'
    assert ('release' in transport.events) == (failure != 'create')
    if failure == 'project':
        transport.connect.assert_not_awaited()
        release = next(r for r in transport.requests if r.method == 'POST' and r.url.path.endswith('/session-one'))
        assert json.loads(release.content)['projectId'] == 'wrong-project'


@pytest.mark.asyncio
async def test_cancellation_after_session_creation_releases_owned_resources(transport):
    transport.connect.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await launch()
    assert transport.events == ['upload', 'create', 'release', 'delete-extension']


@pytest.mark.asyncio
async def test_missing_project_refused_before_any_provider_request(transport):
    with pytest.raises(RuntimeError, match='Browserbase project'):
        await subject.launch_stagehand(BrowserbaseConfig(api_key='fictional', project_id=''), 'context')
    assert not transport.requests


@pytest.mark.asyncio
async def test_app_owned_telemetry_is_explicit_in_installed_sdk_contract(transport):
    from stagehand._generated.models import StagehandInitParams
    _, _, cleanup = await launch()
    telemetry = transport.create.await_args.kwargs['telemetry']
    wire = StagehandInitParams.model_validate({
        'protocol_version': '1.0.0', 'client_info': {'name': 'test', 'version': '1.0.0'},
        'telemetry': telemetry,
    }).model_dump(mode='json', by_alias=True)
    assert wire['telemetry'] == {'traces': {
        'endpoint': 'https://api.jobhunteragent.com/api/stagehand/v1/traces', 'headers': {}}}
    assert 'example.com' not in json.dumps(wire)
    await cleanup.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('origin', [
    None, '', 'http://api.jobhunteragent.com', 'https://localhost',
    'https://127.0.0.1', 'https://example.com',
    'https://user:secret@api.jobhunteragent.com',
    'https://api.jobhunteragent.com/path', 'https://api.jobhunteragent.com?redirect=example.com',
    'https://api.jobhunteragent.com#fragment', 'https://api.jobhunteragent.com:bad',
    'https://api.jobhunteragent.com\\evil',
])
async def test_invalid_telemetry_origin_fails_before_allocating_provider_resources(transport, monkeypatch, origin):
    monkeypatch.setattr(settings, 'BACKEND_PUBLIC_URL', origin)
    with pytest.raises(RuntimeError, match='BACKEND_PUBLIC_URL'):
        await launch()
    assert transport.requests == []
    transport.connect.assert_not_awaited()
    transport.create.assert_not_awaited()
