"""No-network multi-tenant model routing and encrypted-key regressions."""
import asyncio
from unittest.mock import MagicMock

import pytest

from backend.shared import model_access as access, model_key_store as store
from backend.shared.config import settings


@pytest.fixture(autouse=True)
def identities(monkeypatch):
    monkeypatch.setattr(settings, 'BROWSERBASE_CONTEXT_USER_ID', 'owner')
    monkeypatch.setattr(settings, 'LLM_PROVIDER', 'anthropic')
    monkeypatch.setattr(settings, 'ANTHROPIC_API_KEY', 'server-key')
    monkeypatch.setattr(settings, 'ANTHROPIC_WORKSPACE_ID', 'server-workspace')
    monkeypatch.setattr(store, 'get_model_key', lambda uid: {'alice': 'alice-key', 'bob': 'bob-key'}.get(uid))
    with access.model_user_scope(None):
        yield


def test_unbound_factory_fails_before_provider_creation(monkeypatch):
    from backend.shared import llm
    constructor = MagicMock(); monkeypatch.setattr(llm, 'CompatibleChatAnthropic', constructor)
    with pytest.raises(access.ModelAccessRequired): llm.build_llm()
    constructor.assert_not_called()


def test_missing_public_key_never_falls_back_to_owner():
    with access.model_user_scope('visitor'):
        with pytest.raises(access.ModelAccessRequired) as error: access.current_model_credentials()
    assert error.value.status_code == 428


def test_owner_retains_server_account_and_workspace():
    with access.model_user_scope('owner'):
        result = access.current_model_credentials()
    assert result.api_key == 'server-key' and result.server_funded
    assert result.workspace_id == 'server-workspace'
    assert 'server-key' not in repr(result)


@pytest.mark.asyncio
async def test_concurrent_background_tasks_keep_their_own_keys():
    async def worker(user):
        with access.model_user_scope(user):
            await asyncio.sleep(0)
            return access.current_model_credentials()
    a, b = await asyncio.gather(asyncio.create_task(worker('alice')), asyncio.create_task(worker('bob')))
    assert a.api_key == 'alice-key' and b.api_key == 'bob-key'
    assert not a.server_funded and not b.server_funded
    assert a.workspace_id is None and b.workspace_id is None
    assert access.current_model_user() is None


def test_public_factory_does_not_touch_owner_budget(monkeypatch):
    from backend.shared import llm, model_budget
    constructor = MagicMock(); monkeypatch.setattr(llm, 'CompatibleChatAnthropic', constructor)
    monkeypatch.setattr(model_budget, 'configured_ledger', lambda: '/owner/ledger.sqlite')
    monkeypatch.setattr(model_budget, 'Ledger', MagicMock(side_effect=AssertionError('must not touch owner ledger')))
    with access.model_user_scope('alice'):
        llm.build_llm(model='claude-sonnet-5-5')
    assert constructor.call_args.kwargs['api_key'] == 'alice-key'
    assert 'default_headers' not in constructor.call_args.kwargs


def test_owner_factory_keeps_budget_wrapper(monkeypatch):
    from backend.shared import llm, model_budget
    ledger, constructor = MagicMock(), MagicMock()
    monkeypatch.setattr(model_budget, 'configured_ledger', lambda: '/owner/ledger.sqlite')
    monkeypatch.setattr(model_budget, 'Ledger', ledger)
    monkeypatch.setattr(model_budget, 'BudgetChatAnthropic', constructor)
    with access.model_user_scope('owner'): llm.build_llm()
    assert constructor.call_args.kwargs['api_key'] == 'server-key'
    assert constructor.call_args.kwargs['budget_ledger_path'] == '/owner/ledger.sqlite'
    ledger.return_value.snapshot.assert_called_once()


def test_key_saved_encrypted_and_status_does_not_echo_it(monkeypatch):
    from backend.gateway.routes import model_settings
    from backend.shared import credential_store
    monkeypatch.setattr(settings, 'NEXTAUTH_SECRET', 'unit-test-secret')
    monkeypatch.setattr(credential_store, '_fernet', None)
    conn = MagicMock(); conn.__enter__.return_value = conn
    monkeypatch.setattr(store, 'get_connection', lambda: conn)
    store.save_model_key('alice', 'sk-ant-private-alice')
    params = conn.execute.call_args.args[1]
    assert params[0] == 'alice' and 'sk-ant-private-alice' not in params[1]
    assert credential_store._decrypt(params[1]) == {'anthropic_api_key': 'sk-ant-private-alice'}
    monkeypatch.setattr(model_settings, 'get_model_key', lambda uid: 'sk-ant-private-alice')
    response = model_settings.public_settings('alice')
    assert response['ready'] and response['anthropic_key_hint'] == '…lice'
    assert 'sk-ant-private-alice' not in str(response)


@pytest.mark.asyncio
async def test_stagehand_callback_is_bound_even_in_another_dispatch_context(monkeypatch):
    from unittest.mock import AsyncMock
    from backend.browser import stagehand_session as session
    from backend.browser.browserbase_client import BrowserbaseConfig
    browser = MagicMock()
    browser.session_id = 'offline-session'; browser.close = AsyncMock()
    monkeypatch.setattr(session.browserbase, 'launch', AsyncMock(return_value=browser))
    agent = MagicMock(); agent.close = AsyncMock()
    create = AsyncMock(return_value=agent); monkeypatch.setattr(session.Stagehand, 'create', create)
    response = MagicMock(); response.json.return_value = {'connectUrl': 'wss://offline', 'debuggerUrl': 'https://offline'}
    client = MagicMock(); client.__aenter__ = AsyncMock(return_value=client); client.__aexit__ = AsyncMock()
    client.get = AsyncMock(return_value=response)
    monkeypatch.setattr(session.httpx, 'AsyncClient', lambda **_: client)
    async def inspect_identity(_): return access.current_model_credentials().api_key
    monkeypatch.setattr(session, 'generate', inspect_identity)
    with access.model_user_scope('alice'):
        _, _, cleanup = await session.launch_stagehand(BrowserbaseConfig(api_key='alice-browser-key', project_id='alice-project'), 'alice-context')
    callback = create.call_args.kwargs['model']
    with access.model_user_scope('bob'):
        assert await callback(None) == 'alice-key'
        assert access.current_model_user() == 'bob'
    assert access.current_model_user() is None
    await cleanup.aclose()


@pytest.mark.asyncio
async def test_public_user_cannot_spend_server_skyvern_validation(monkeypatch):
    from backend.gateway.routes import credentials
    monkeypatch.setattr(credentials, 'get_credential', MagicMock(side_effect=AssertionError('must not start validation')))
    response = await credentials.validate_board_credential(credentials.ValidateCredentialRequest(board='indeed'), user={'id': 'alice'})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_account_deletion_stops_if_owned_model_key_cannot_be_removed(monkeypatch):
    from backend.gateway.routes import auth
    monkeypatch.setattr(auth, 'get_current_user', lambda _: {'id': 'alice', 'email': 'alice@example.com'})
    remove = MagicMock(side_effect=RuntimeError('storage unavailable'))
    monkeypatch.setattr(store, 'save_model_key', remove)
    billing_delete = MagicMock()
    monkeypatch.setattr('backend.shared.billing_store.delete_user_data', billing_delete)
    with pytest.raises(Exception) as error:
        await auth.delete_user_data(None)
    assert error.value.status_code == 503
    remove.assert_called_once_with('alice', '')
    billing_delete.assert_not_called()



def test_public_settings_never_reads_or_exposes_owner_ledger(monkeypatch):
    from backend.gateway.routes import model_settings
    from backend.shared import model_budget
    monkeypatch.setattr(model_settings, 'get_model_key', lambda _: 'alice-key')
    monkeypatch.setattr(model_budget, 'configured_ledger', MagicMock(side_effect=AssertionError('no owner ledger reads')))
    response = model_settings.public_settings('alice')
    assert response['budget'] is None and response['funding'] == 'own_keys'
    assert response['models']['default'] == settings.ANTHROPIC_DEFAULT_MODEL


def test_owner_settings_exposes_only_aggregate_budget(monkeypatch, tmp_path):
    from backend.gateway.routes import model_settings
    from backend.shared.model_budget import Ledger, MODEL
    path = tmp_path / 'private-ledger.sqlite'
    ledger = Ledger.create(path, limit_usd='25')
    first = ledger.reserve(2_000_000); ledger.settle(first, 100_000, {'private': 'do-not-expose'})
    ledger.reserve(500_000)
    before = ledger.snapshot()
    monkeypatch.setenv('JOBHUNTER_MODEL_BUDGET_LEDGER', str(path))
    monkeypatch.setattr(model_settings, 'get_model_key', lambda _: None)
    response = model_settings.public_settings('owner')
    assert response['budget'] == {'status':'available', 'currency':'USD', 'cap':'25.000000',
                                  'settled':'0.100000', 'reserved':'0.500000', 'remaining':'24.400000'}
    assert set(response['models'].values()) == {MODEL}
    assert 'private' not in str(response) and 'do-not-expose' not in str(response)
    assert str(path) not in str(response)
    assert ledger.snapshot() == before


def test_public_browser_readout_matches_stagehand_callback_model(monkeypatch):
    from backend.gateway.routes import model_settings
    monkeypatch.setattr(model_settings, 'get_model_key', lambda _: 'alice-key')
    monkeypatch.setattr(settings, 'BROWSER_MODE', 'browserbase')
    monkeypatch.setattr(settings, 'ANTHROPIC_BROWSER_MODEL', 'claude-haiku-4-5-20251001')
    response = model_settings.public_settings('alice')
    assert response['models']['browser'] == settings.ANTHROPIC_DEFAULT_MODEL
