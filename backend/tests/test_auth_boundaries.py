"""Offline regressions for account and session trust boundaries."""
import base64
import json
import os
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException
from starlette.requests import Request

from backend.gateway.middleware import jwt_auth


def request(token=None):
    headers = [(b'authorization', f'Bearer {token}'.encode())] if token else []
    return Request({'type': 'http', 'method': 'GET', 'path': '/api/auth/me', 'headers': headers, 'query_string': b''})


def token(payload, secret='test-secret'):
    enc = lambda b: base64.urlsafe_b64encode(b).rstrip(b'=').decode()
    header = enc(b'{"alg":"dir","enc":"A256GCM"}')
    iv = os.urandom(12)
    data = AESGCM(jwt_auth._derive_encryption_key(secret)).encrypt(iv, json.dumps(payload).encode(), header.encode())
    return '.'.join([header, '', enc(iv), enc(data[:-16]), enc(data[-16:])])


@pytest.mark.parametrize('exp', [None, 0, time.time()-60, 'tomorrow', True, float('inf')])
def test_invalid_expiration_cannot_authenticate(monkeypatch, exp):
    monkeypatch.setattr(jwt_auth, 'get_settings', lambda: SimpleNamespace(NEXTAUTH_SECRET='test-secret'))
    assert jwt_auth._extract_email(request(token({'email': 'owner@example.com', 'exp': exp}))) is None


def test_current_jwe_authenticates(monkeypatch):
    monkeypatch.setattr(jwt_auth, 'get_settings', lambda: SimpleNamespace(NEXTAUTH_SECRET='test-secret'))
    assert jwt_auth._extract_email(request(token({'email': 'owner@example.com', 'exp': time.time()+300}))) == 'owner@example.com'


def test_trial_identity_cannot_resolve_a_real_user(monkeypatch):
    from backend.gateway.deps import get_current_user
    monkeypatch.setattr('backend.shared.billing_store.get_user_by_id', lambda _: {'id': 'owner', 'email': 'owner@example.com'})
    req = request(); req.state.user_email = None; req.state.trial_user_id = 'owner'
    with pytest.raises(HTTPException) as error:
        get_current_user(req)
    assert error.value.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize('owner,status', [(None,404), ('other',403), ('me',None)])
async def test_owner_must_be_verified_in_durable_session(monkeypatch, owner, status):
    from backend.gateway.deps import verify_session_owner
    from backend.gateway.routes.sessions import session_registry
    monkeypatch.setattr('backend.gateway.routes.sessions.session_registry', {})
    monkeypatch.setattr('backend.shared.session_store.get_session_by_id', lambda _: {'user_id': owner} if owner else None)
    req = request(); req.scope['app'] = SimpleNamespace(state=SimpleNamespace(checkpointer=None))
    if status:
        with pytest.raises(HTTPException) as error:
            await verify_session_owner('unowned', {'id': 'me'}, req)
        assert error.value.status_code == status
    else:
        await verify_session_owner('owned', {'id': 'me'}, req)


@pytest.mark.asyncio
async def test_trial_start_cannot_mint_owner_token(monkeypatch):
    from backend.gateway.routes.free_trial import free_trial_start
    from backend.shared.models.schemas import StartSessionRequest
    monkeypatch.setattr('backend.shared.billing_store.get_or_create_user', lambda _: pytest.fail('must not resolve a claimed email'))
    with pytest.raises(HTTPException) as error:
        await free_trial_start(StartSessionRequest(resume_text='Owner owner@example.com'), request())
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_trial_convert_requires_verified_signin():
    from backend.gateway.routes.free_trial import free_trial_convert, ConvertRequest
    with pytest.raises(HTTPException) as error:
        await free_trial_convert(ConvertRequest(trial_token='legacy', password='a-long-password'), request())
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_totp_requires_auth_before_reading_mail(monkeypatch):
    from backend.gateway.routes.sessions import get_totp_code
    monkeypatch.setattr('backend.shared.gmail_client.poll_for_verification_code', AsyncMock(side_effect=AssertionError('must not poll mail')))
    with pytest.raises(HTTPException) as error:
        await get_totp_code('victim-session', request())
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_debug_application_cannot_launch_paid_work():
    from backend.gateway.routes.sessions import test_apply_endpoint, TestApplyRequest
    with pytest.raises(HTTPException) as error:
        await test_apply_endpoint(TestApplyRequest(job_url='https://www.indeed.com/viewjob?jk=test'), request())
    assert error.value.status_code == 410


def test_concurrent_signup_preserves_existing_credits(monkeypatch):
    from backend.shared import billing_store
    first, second = MagicMock(), MagicMock()
    first.__enter__.return_value = first
    second.__enter__.return_value = second
    first.execute.return_value.fetchone.return_value = None
    # The other request has already consumed a free credit when we re-read.
    second.execute.return_value.fetchone.return_value = (
        'existing-id', 'new@example.com', 0, 2, False, None, 'google', None,
        'email', None, [], 0, '',
    )
    connections = iter([first, second])
    monkeypatch.setattr(billing_store, '_connect', lambda: next(connections))
    monkeypatch.setattr(billing_store, 'get_settings', lambda: SimpleNamespace(STRIPE_SECRET_KEY=None))
    result = billing_store.get_or_create_user('new@example.com')
    assert result['id'] == 'existing-id'
    assert result['free_applications_remaining'] == 2
    assert 'ON CONFLICT (email) DO NOTHING' in first.execute.call_args_list[1].args[0]
    first.commit.assert_called_once()


def test_new_verified_account_receives_three_free_credits(monkeypatch):
    from backend.shared import billing_store
    connection = MagicMock(); connection.__enter__.return_value = connection
    select, insert = MagicMock(), MagicMock()
    select.fetchone.return_value = None; insert.fetchone.return_value = ('new-id',)
    connection.execute.side_effect = [select, insert]
    monkeypatch.setattr(billing_store, '_connect', lambda: connection)
    monkeypatch.setattr(billing_store, 'get_settings', lambda: SimpleNamespace(STRIPE_SECRET_KEY=None))
    result = billing_store.get_or_create_user('new@example.com')
    assert result['free_applications_remaining'] == 3
    assert result['is_premium'] is False
    assert result['wallet_balance'] == 0
    connection.commit.assert_called_once()


@pytest.mark.asyncio
async def test_resume_download_token_is_bound_to_session(monkeypatch):
    import hashlib, hmac
    from backend.gateway.routes.sessions import serve_resume_file
    from backend.shared.config import settings
    monkeypatch.setattr(settings, 'NEXTAUTH_SECRET', 'download-test')
    payload = f'owned-session:{int(time.time())}'
    signature = hmac.new(b'download-test', payload.encode(), hashlib.sha256).hexdigest()[:32]
    with pytest.raises(HTTPException) as error:
        await serve_resume_file('someone-elses-session', request(), f'{payload}.{signature}')
    assert error.value.status_code == 403
