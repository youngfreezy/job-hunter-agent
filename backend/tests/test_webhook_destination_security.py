from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.shared import webhook_url, webhook_store, webhook_dispatcher


@pytest.mark.parametrize('url', ['http://example.com/hook','https://user:pass@example.com/hook',
    'https://example.com/#fragment','https://127.0.0.1/hook','https://[::1]/hook',
    'https://169.254.169.254/latest/meta-data'])
def test_unsafe_destinations_cannot_be_registered_or_updated(monkeypatch,url):
    address='::1' if '[::1]' in url else '127.0.0.1'
    monkeypatch.setattr(webhook_url.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',(address,443))])
    db=MagicMock(side_effect=AssertionError('No DB write for rejected URL'))
    monkeypatch.setattr(webhook_store,'get_connection',db)
    for operation in (lambda:webhook_store.create_webhook('u',url,['agent.completed']),
                      lambda:webhook_store.update_webhook('w','u',url=url)):
        with pytest.raises(ValueError,match='public internet'): operation()
    db.assert_not_called()


def test_mixed_public_private_dns_is_rejected(monkeypatch):
    monkeypatch.setattr(webhook_url.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('8.8.8.8',443)),(10,1,6,'',('fd00::1',443))])
    with pytest.raises(ValueError):webhook_url.validate_webhook_url('https://fixture.example/hook')


@pytest.mark.asyncio
async def test_saved_url_revalidated_before_delivery_and_no_sensitive_response_recorded(monkeypatch):
    monkeypatch.setattr(webhook_url.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('10.0.0.1',443))])
    client=MagicMock(side_effect=AssertionError('No outbound request for internal address'))
    monkeypatch.setattr(webhook_dispatcher.httpx,'AsyncClient',client)
    log=MagicMock();monkeypatch.setattr(webhook_dispatcher,'log_delivery',log)
    await webhook_dispatcher._deliver_single({'id':'w','url':'https://fixture.example/hook','secret':'fixture'},'agent.completed',{})
    client.assert_not_called()
    assert log.call_args.kwargs['success'] is False
    assert log.call_args.kwargs['response_status'] is None
    assert '10.0.0.1' not in log.call_args.kwargs['response_body']


@pytest.mark.asyncio
async def test_public_destination_disables_redirects(monkeypatch):
    monkeypatch.setattr(webhook_url.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('8.8.8.8',443))])
    client=MagicMock();client.__aenter__=AsyncMock(return_value=client);client.__aexit__=AsyncMock()
    client.post=AsyncMock(return_value=MagicMock(status_code=204,text=''))
    factory=MagicMock(return_value=client);monkeypatch.setattr(webhook_dispatcher.httpx,'AsyncClient',factory)
    monkeypatch.setattr(webhook_dispatcher,'log_delivery',MagicMock())
    await webhook_dispatcher._deliver_single({'id':'w','url':'https://fixture.example/hook','secret':'fixture'},'agent.completed',{})
    assert factory.call_args.kwargs['follow_redirects'] is False
    client.post.assert_awaited_once()

@pytest.mark.asyncio
async def test_delivery_pins_ip_and_preserves_tls_name(monkeypatch):
    dns=MagicMock(side_effect=[[(2,1,6,'',('8.8.8.8',8443))],[(2,1,6,'',('127.0.0.1',8443))]])
    monkeypatch.setattr(webhook_url.socket,'getaddrinfo',dns)
    client=MagicMock();client.__aenter__=AsyncMock(return_value=client);client.__aexit__=AsyncMock()
    client.post=AsyncMock(return_value=MagicMock(status_code=204,text=''))
    factory=MagicMock(return_value=client);monkeypatch.setattr(webhook_dispatcher.httpx,'AsyncClient',factory)
    monkeypatch.setattr(webhook_dispatcher,'log_delivery',MagicMock())
    await webhook_dispatcher._deliver_single({'id':'w','url':'https://fixture.example:8443/hook?q=1','secret':'fixture'},'agent.completed',{})
    args,kwargs=client.post.call_args
    assert str(args[0])=='https://8.8.8.8:8443/hook?q=1'
    assert kwargs['headers']['Host']=='fixture.example:8443'
    assert kwargs['extensions']['sni_hostname']=='fixture.example'
    assert factory.call_args.kwargs['trust_env'] is False
    assert dns.call_count==1

@pytest.mark.asyncio
async def test_httpcore_uses_pinned_tcp_target_and_original_tls_identity():
    """Exercise installed transport implementation without opening any socket."""
    import httpcore
    from httpcore._async.connection import AsyncHTTPConnection
    backend=MagicMock()
    stream=MagicMock();stream.start_tls=AsyncMock(return_value=stream)
    backend.connect_tcp=AsyncMock(return_value=stream)
    origin=httpcore.Origin(scheme=b'https',host=b'8.8.8.8',port=443)
    connection=AsyncHTTPConnection(origin=origin,network_backend=backend)
    request=httpcore.Request('POST','https://8.8.8.8/hook',extensions={'sni_hostname':'fixture.example'})
    await connection._connect(request)
    assert backend.connect_tcp.call_args.kwargs['host']=='8.8.8.8'
    assert stream.start_tls.call_args.kwargs['server_hostname']=='fixture.example'
    context=stream.start_tls.call_args.kwargs['ssl_context']
    assert context.check_hostname and context.verify_mode != 0
