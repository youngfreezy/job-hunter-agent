"""Offline abuse case for a bearer token exposed through an SSE URL."""
import time
from unittest.mock import patch

from starlette.requests import Request

from backend.gateway.middleware import jwt_auth


def test_query_string_bearer_cannot_authenticate_an_unrelated_mutation(monkeypatch):
    # Synthetic token only: no browser credentials or production requests.
    request = Request({'type':'http', 'method':'DELETE', 'path':'/api/auth/me',
                       'query_string':b'token=fake-audit-token', 'headers':[]})
    monkeypatch.setattr(jwt_auth, 'get_settings', lambda: type('Settings', (), {'NEXTAUTH_SECRET':'fixture'})())
    monkeypatch.setattr(jwt_auth, 'decrypt_nextauth_jwt', lambda *_: {
        'email':'fixture@example.test', 'exp':time.time()+300})
    assert jwt_auth._extract_email(request) is None


def test_access_log_redacts_legacy_query_before_formatting():
    import logging
    from uvicorn.protocols.utils import get_path_with_query_string
    from backend.gateway.access_logging import RedactAccessQuery
    path = get_path_with_query_string({'path':'/api/sessions/fixture/stream',
                                      'query_string':b'token=fake-audit-token&access_token=another-secret'})
    record = logging.LogRecord('uvicorn.access', logging.INFO, '', 0,
                               '%s - "%s %s HTTP/%s" %d',
                               ('127.0.0.1', 'GET', path, '1.1', 401), None)
    assert RedactAccessQuery().filter(record)
    rendered = record.getMessage()
    assert '/api/sessions/fixture/stream?[redacted]' in rendered
    assert 'fake-audit-token' not in rendered and 'another-secret' not in rendered
    assert '401' in rendered


def test_bearer_header_auth_still_works(monkeypatch):
    request = Request({'type':'http','method':'GET','path':'/api/sessions/fixture/stream',
                       'query_string':b'', 'headers':[(b'authorization',b'Bearer fixture')]})
    monkeypatch.setattr(jwt_auth, 'get_settings', lambda: type('Settings', (), {'NEXTAUTH_SECRET':'fixture'})())
    monkeypatch.setattr(jwt_auth, 'decrypt_nextauth_jwt', lambda *_: {
        'email':'fixture@example.test','exp':time.time()+300})
    assert jwt_auth._extract_email(request) == 'fixture@example.test'
