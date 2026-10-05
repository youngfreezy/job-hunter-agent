"""The Stagehand collector discards sensitive traces without reading the body."""
from unittest.mock import AsyncMock

import httpx
import pytest

PATH = '/api/stagehand/v1/traces'


@pytest.mark.asyncio
@pytest.mark.parametrize('method', ['POST', 'OPTIONS'])
async def test_discard_endpoint_never_reads_or_logs_body_with_full_middleware(method, caplog):
    from backend.gateway.main import create_app
    marker = 'synthetic-applicant-secret-never-read-or-log'
    receive = AsyncMock(side_effect=AssertionError(marker))
    send = AsyncMock()
    scope = {
        'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
        'method': method, 'scheme': 'https', 'path': PATH,
        'raw_path': PATH.encode(), 'query_string': b'', 'root_path': '',
        'server': ('api.jobhunteragent.com', 443), 'client': ('127.0.0.1', 12345),
        'headers': [(b'host', b'api.jobhunteragent.com'),
                    (b'origin', b'chrome-extension://abcdefghijklmnopqrstuvwxyzabcdef'),
                    (b'content-type', b'application/json'),
                    (b'access-control-request-method', b'POST'),
                    (b'access-control-request-headers', b'content-type')],
    }
    await create_app()(scope, receive, send)
    receive.assert_not_awaited()
    messages = [call.args[0] for call in send.await_args_list]
    start = next(message for message in messages if message['type'] == 'http.response.start')
    assert start['status'] == 204
    headers = dict(start['headers'])
    assert headers[b'access-control-allow-origin'] == b'*'
    assert b'POST' in headers[b'access-control-allow-methods']
    assert b'content-type' in headers[b'access-control-allow-headers']
    assert b'access-control-allow-credentials' not in headers
    assert b'set-cookie' not in headers
    assert b''.join(m.get('body', b'') for m in messages) == b''
    assert marker not in caplog.text


@pytest.mark.asyncio
async def test_collector_does_not_exempt_other_posts_from_csrf():
    from backend.gateway.main import create_app
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url='https://api.jobhunteragent.com') as client:
        response = await client.post(PATH + '/different-route', content='synthetic-secret')
    assert response.status_code == 403
