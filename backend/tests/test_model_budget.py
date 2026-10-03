from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.shared.model_budget import BudgetStopped, Ledger, BudgetChatAnthropic


def test_reservations_are_atomic_and_persist_across_restart(tmp_path):
    path = tmp_path / 'budget.sqlite'
    Ledger.create(path, limit_usd='12')
    def reserve(_):
        try:
            return Ledger(path).reserve(3_100_000)
        except BudgetStopped:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        reservations = list(pool.map(reserve, range(8)))
    assert sum(item is not None for item in reservations) == 3
    assert Ledger(path).snapshot()['committed_microusd'] == 9_300_000
    with pytest.raises(BudgetStopped):
        Ledger(path).reserve(3_100_000)


def test_settlement_releases_only_known_usage_and_does_not_reset_limit(tmp_path):
    path = tmp_path / 'budget.sqlite'
    Ledger.create(path, limit_usd='12')
    ledger = Ledger(path)
    reservation = ledger.reserve(3_122_880)
    ledger.settle(reservation, 120_000, {'input_tokens': 30000, 'output_tokens': 2000})
    assert Ledger(path).snapshot()['committed_microusd'] == 120_000
    with pytest.raises(BudgetStopped):
        Ledger.create(path, limit_usd='15')
    assert Ledger(path).snapshot()['limit_microusd'] == 12_000_000


def test_missing_or_corrupt_ledger_fails_closed(tmp_path):
    path = tmp_path/'missing.sqlite'
    with pytest.raises(BudgetStopped):
        Ledger(path).reserve(1)
    assert not path.exists()
    path.write_text('bad')
    with pytest.raises(BudgetStopped):
        Ledger(path).reserve(1)


@pytest.fixture
def model(tmp_path):
    path = tmp_path/'budget.sqlite'
    Ledger.create(path, limit_usd='12')
    return BudgetChatAnthropic(model='claude-sonnet-4-6', api_key='test',
                               max_tokens=8192, max_retries=0,
                               disable_streaming=True, budget_ledger_path=str(path))


def payload(**kwargs):
    return {'model': 'claude-sonnet-4-6', 'max_tokens': 8192,
            'messages': [{'role': 'user', 'content': 'hello'}], **kwargs}


@pytest.mark.asyncio
async def test_dispatch_reserves_max_context_then_settles_usage(model, monkeypatch):
    async def dispatch(self, request):
        assert Ledger(model.budget_ledger_path).snapshot()['committed_microusd'] == 3_122_880
        assert request['service_tier'] == 'standard_only'
        return SimpleNamespace(usage=SimpleNamespace(input_tokens=1000, output_tokens=100,
                               cache_creation_input_tokens=0, cache_read_input_tokens=0))
    monkeypatch.setattr('langchain_anthropic.ChatAnthropic._acreate', dispatch)
    await model._acreate(payload())
    assert Ledger(model.budget_ledger_path).snapshot()['committed_microusd'] == 4500


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [TimeoutError(), __import__('asyncio').CancelledError()])
async def test_uncertain_dispatch_keeps_full_reservation(model, monkeypatch, error):
    dispatch = AsyncMock(side_effect=error)
    monkeypatch.setattr('langchain_anthropic.ChatAnthropic._acreate', dispatch)
    with pytest.raises(type(error)):
        await model._acreate(payload())
    assert Ledger(model.budget_ledger_path).snapshot()['committed_microusd'] == 3_122_880
    assert dispatch.await_count == 1


@pytest.mark.asyncio
async def test_missing_usage_keeps_reservation_and_stops(model, monkeypatch):
    monkeypatch.setattr('langchain_anthropic.ChatAnthropic._acreate', AsyncMock(return_value=SimpleNamespace(usage=None)))
    with pytest.raises(BudgetStopped):
        await model._acreate(payload())
    assert Ledger(model.budget_ledger_path).snapshot()['committed_microusd'] == 3_122_880


@pytest.mark.asyncio
@pytest.mark.parametrize('overrides', [
    {'model': 'claude-opus-4-6'}, {'max_tokens': 200000}, {'stream': True},
    {'cache_control': {'type': 'ephemeral'}}, {'tools': [{'type': 'web_search_20250305', 'name': 'web_search'}]},
    {'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': 'hi', 'cache_control': {'type': 'ephemeral'}}]}]},
    {'service_tier': 'auto'}, {'inference_geo': 'us'}, {'mcp_servers': [{'name': 'remote'}]},
])
async def test_unpriced_request_features_never_dispatch(model, monkeypatch, overrides):
    dispatch = AsyncMock()
    monkeypatch.setattr('langchain_anthropic.ChatAnthropic._acreate', dispatch)
    request = payload()
    request.update(overrides)
    with pytest.raises(BudgetStopped):
        await model._acreate(request)
    dispatch.assert_not_awaited()
    assert Ledger(model.budget_ledger_path).snapshot()['committed_microusd'] == 0


def test_build_llm_pins_all_models_and_blocks_alternate_client(monkeypatch, tmp_path):
    from backend.shared import llm
    path = tmp_path/'budget.sqlite'
    Ledger.create(path, limit_usd='12')
    monkeypatch.setenv('JOBHUNTER_MODEL_BUDGET_LEDGER', str(path))
    monkeypatch.setattr(llm, 'get_settings', lambda: SimpleNamespace(LLM_PROVIDER='anthropic',
        ANTHROPIC_API_KEY='test', ANTHROPIC_WORKSPACE_ID='', ANTHROPIC_DEFAULT_MODEL='claude-sonnet-4-6'))
    instance = llm.build_llm(model='claude-opus-4-6')
    assert isinstance(instance, BudgetChatAnthropic)
    assert instance.model == 'claude-sonnet-4-6'
    assert instance.max_retries == 0
    assert instance.disable_streaming is True
    with pytest.raises(BudgetStopped):
        llm.build_browser_use_llm()


@pytest.mark.asyncio
async def test_real_structured_output_chain_cannot_bypass_guard(model, monkeypatch):
    from anthropic.types import Message, ToolUseBlock, Usage
    async def dispatch(self, request):
        assert Ledger(model.budget_ledger_path).snapshot()['committed_microusd'] == 3_122_880
        name = request['tools'][0]['name']
        return Message(id='fixture', model='claude-sonnet-4-6', role='assistant', type='message',
            stop_reason='tool_use', content=[ToolUseBlock(id='tool', type='tool_use', name=name, input={'kind': 'park'})],
            usage=Usage(input_tokens=2000, output_tokens=100))
    monkeypatch.setattr('langchain_anthropic.ChatAnthropic._acreate', dispatch)
    result = await model.with_structured_output({'title': 'Decision', 'type': 'object',
        'properties': {'kind': {'type': 'string'}}, 'required': ['kind']}, include_raw=True).ainvoke('Choose next step')
    assert result['parsed'] == {'kind': 'park'}
    assert Ledger(model.budget_ledger_path).snapshot()['committed_microusd'] == 7500


def test_real_sync_invoke_is_charged(model, monkeypatch):
    from anthropic.types import Message, TextBlock, Usage
    def dispatch(self, request):
        assert Ledger(model.budget_ledger_path).snapshot()['committed_microusd'] == 3_122_880
        return Message(id='fixture', model='claude-sonnet-4-6', role='assistant', type='message',
            stop_reason='end_turn', content=[TextBlock(type='text', text='grounded')],
            usage=Usage(input_tokens=2000, output_tokens=100))
    monkeypatch.setattr('langchain_anthropic.ChatAnthropic._create', dispatch)
    assert model.invoke('Check these facts').content == 'grounded'
    assert Ledger(model.budget_ledger_path).snapshot()['committed_microusd'] == 7500


def test_fresh_process_keeps_existing_reservations(tmp_path):
    import subprocess
    import sys
    path = tmp_path/'budget.sqlite'
    Ledger.create(path, limit_usd='12').reserve(9_000_000)
    code = ('import sys; from backend.shared.model_budget import Ledger, BudgetStopped; '
            'Ledger(sys.argv[1]).reserve(4_000_000)')
    result = subprocess.run([sys.executable, '-c', code, str(path)], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'Model spend ceiling reached' in result.stderr
    assert Ledger(path).snapshot()['committed_microusd'] == 9_000_000
