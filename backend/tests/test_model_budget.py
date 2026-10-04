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
def model(tmp_path, monkeypatch):
    path = tmp_path/'budget.sqlite'
    from backend.shared import llm
    Ledger.create(path, limit_usd='18')
    monkeypatch.setenv('JOBHUNTER_MODEL_BUDGET_LEDGER', str(path))
    monkeypatch.setattr(llm, 'get_settings', lambda: SimpleNamespace(LLM_PROVIDER='anthropic',
        ANTHROPIC_API_KEY='test', ANTHROPIC_WORKSPACE_ID='', ANTHROPIC_DEFAULT_MODEL='claude-sonnet-4-6'))
    return llm.build_llm(model='claude-sonnet-4-6', max_tokens=8192)


def payload(**kwargs):
    return {'model': 'claude-sonnet-5-5', 'max_tokens': 8192,
            'messages': [{'role': 'user', 'content': 'hello'}], **kwargs}


@pytest.mark.asyncio
async def test_dispatch_reserves_max_context_then_settles_usage(model, monkeypatch):
    async def dispatch(self, request):
        assert Ledger(model.budget_ledger_path).snapshot()['committed_microusd'] == 2_081_920
        assert request['service_tier'] == 'standard_only'
        return SimpleNamespace(usage=SimpleNamespace(input_tokens=1000, output_tokens=100,
                               cache_creation_input_tokens=0, cache_read_input_tokens=0))
    monkeypatch.setattr('langchain_anthropic.ChatAnthropic._acreate', dispatch)
    await model._acreate(payload())
    assert Ledger(model.budget_ledger_path).snapshot()['committed_microusd'] == 3000


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [TimeoutError(), __import__('asyncio').CancelledError()])
async def test_uncertain_dispatch_keeps_full_reservation(model, monkeypatch, error):
    dispatch = AsyncMock(side_effect=error)
    monkeypatch.setattr('langchain_anthropic.ChatAnthropic._acreate', dispatch)
    with pytest.raises(type(error)):
        await model._acreate(payload())
    assert Ledger(model.budget_ledger_path).snapshot()['committed_microusd'] == 2_081_920
    assert dispatch.await_count == 1


@pytest.mark.asyncio
async def test_missing_usage_keeps_reservation_and_stops(model, monkeypatch):
    monkeypatch.setattr('langchain_anthropic.ChatAnthropic._acreate', AsyncMock(return_value=SimpleNamespace(usage=None)))
    with pytest.raises(BudgetStopped):
        await model._acreate(payload())
    assert Ledger(model.budget_ledger_path).snapshot()['committed_microusd'] == 2_081_920


@pytest.mark.asyncio
@pytest.mark.parametrize('overrides', [
    {'model': 'claude-opus-4-6'}, {'model': 'claude-sonnet-4-6'},
    {'model': 'claude-sonnet-4-5'}, {'max_tokens': 128001}, {'stream': True},
    {'betas': ['context-1m-2025-08-07']},
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
    assert instance.model == 'claude-sonnet-5-5'
    assert instance.max_retries == 0
    assert instance.disable_streaming is True
    with pytest.raises(BudgetStopped):
        llm.build_browser_use_llm()


@pytest.mark.asyncio
async def test_real_structured_output_chain_cannot_bypass_guard(model, monkeypatch):
    from anthropic.types import Message, TextBlock, ThinkingBlock, Usage
    async def dispatch(self, request):
        assert Ledger(model.budget_ledger_path).snapshot()['committed_microusd'] == 2_081_920
        assert request['model'] == 'claude-sonnet-5-5'
        assert request['max_tokens'] == 8192
        assert 'tool_choice' not in request and 'tools' not in request
        assert request['output_config']['format']['type'] == 'json_schema'
        assert 'output_format' not in request and request['betas'] == []
        assert 'temperature' not in request
        assert request['thinking'] == {'type': 'between_tools'}
        return Message(id='fixture', model='claude-sonnet-5-5', role='assistant', type='message',
            stop_reason='end_turn', content=[ThinkingBlock(type='thinking', thinking='fixture', signature='fixture'), TextBlock(type='text', text='{"kind": "park"}')],
            usage=Usage(input_tokens=2000, output_tokens=100))
    monkeypatch.setattr('langchain_anthropic.ChatAnthropic._acreate', dispatch)
    result = await model.with_structured_output({'title': 'Decision', 'type': 'object',
        'properties': {'kind': {'type': 'string'}}, 'required': ['kind']}, include_raw=True).ainvoke('Choose next step')
    assert result['parsed'] == {'kind': 'park'}
    assert Ledger(model.budget_ledger_path).snapshot()['committed_microusd'] == 5000


def test_real_sync_structured_invoke_is_charged(model, monkeypatch):
    from anthropic.types import Message, TextBlock, ThinkingBlock, Usage
    def dispatch(self, request):
        assert Ledger(model.budget_ledger_path).snapshot()['committed_microusd'] == 2_081_920
        assert request['model'] == 'claude-sonnet-5-5'
        assert request['max_tokens'] == 8192
        assert 'tool_choice' not in request and 'tools' not in request
        assert request['output_config']['format']['type'] == 'json_schema'
        assert 'output_format' not in request and request['betas'] == []
        assert 'temperature' not in request
        assert request['thinking'] == {'type': 'between_tools'}
        return Message(id='fixture', model='claude-sonnet-5-5', role='assistant', type='message',
            stop_reason='end_turn', content=[ThinkingBlock(type='thinking', thinking='fixture', signature='fixture'), TextBlock(type='text', text='{"kind": "park"}')],
            usage=Usage(input_tokens=2000, output_tokens=100))
    monkeypatch.setattr('langchain_anthropic.ChatAnthropic._create', dispatch)
    result = model.with_structured_output({'title': 'Decision', 'type': 'object',
        'properties': {'kind': {'type': 'string'}}, 'required': ['kind']}, include_raw=True).invoke('Check these facts')
    assert result['parsed'] == {'kind': 'park'}
    assert Ledger(model.budget_ledger_path).snapshot()['committed_microusd'] == 5000


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


@pytest.mark.asyncio
async def test_smaller_future_reservations_never_reprice_existing_holds(model, monkeypatch):
    import sqlite3
    ledger = Ledger(model.budget_ledger_path)
    settled = ledger.reserve(11_400_594)
    ledger.settle(settled, 11_400_594, {'historical_usage': True})
    old_hold = ledger.reserve(3_015_360)  # Prior Sonnet 4.6 request, still unknown.
    contingency = ledger.reserve(500_000)
    before = ledger.snapshot()
    assert before == {'limit_microusd': 18_000_000, 'committed_microusd': 14_915_954}
    async def dispatch(self, request):
        assert request['model'] == 'claude-sonnet-5-5'
        assert ledger.snapshot()['committed_microusd'] == 14_915_954 + 2_081_920
        return SimpleNamespace(usage=SimpleNamespace(input_tokens=2000, output_tokens=100))
    monkeypatch.setattr('langchain_anthropic.ChatAnthropic._acreate', dispatch)
    await model._acreate(payload())
    assert ledger.snapshot() == {'limit_microusd': 18_000_000, 'committed_microusd': 14_920_954}
    with sqlite3.connect(model.budget_ledger_path) as db:
        assert db.execute('SELECT reserved, charged FROM calls WHERE id=?', (old_hold,)).fetchone() == (3_015_360, None)
        assert db.execute('SELECT reserved, charged FROM calls WHERE id=?', (contingency,)).fetchone() == (500_000, None)


@pytest.mark.asyncio
@pytest.mark.parametrize('usage', [
    {'input_tokens': 1_000_001, 'output_tokens': 1},
    {'input_tokens': 1, 'output_tokens': 8193},
])
async def test_usage_outside_pinned_bounds_retains_full_new_hold(model, monkeypatch, usage):
    monkeypatch.setattr('langchain_anthropic.ChatAnthropic._acreate',
                        AsyncMock(return_value=SimpleNamespace(usage=SimpleNamespace(**usage))))
    with pytest.raises(BudgetStopped, match='Unexpected provider billing'):
        await model._acreate(payload())
    assert Ledger(model.budget_ledger_path).snapshot()['committed_microusd'] == 2_081_920


def test_unguarded_factory_keeps_requested_model(model, monkeypatch):
    from backend.shared import llm
    from langchain_anthropic import ChatAnthropic
    monkeypatch.delenv('JOBHUNTER_MODEL_BUDGET_LEDGER')
    instance = llm.build_llm(model='claude-sonnet-4-6')
    assert type(instance) is ChatAnthropic
    assert instance.model == 'claude-sonnet-4-6'


@pytest.mark.asyncio
async def test_stagehand_sdk_callback_uses_actual_latest_budget_model(model, monkeypatch):
    from anthropic.types import Message, TextBlock, ThinkingBlock, Usage
    from stagehand import LLMStructuredGenerateParams
    from backend.browser.stagehand_model import generate
    async def dispatch(self, request):
        assert request['model'] == 'claude-sonnet-5-5'
        assert request['max_tokens'] == 8192
        assert self.max_retries == 0
        assert Ledger(model.budget_ledger_path).snapshot()['committed_microusd'] == 2_081_920
        assert 'tool_choice' not in request and 'tools' not in request
        assert request['output_config']['format']['type'] == 'json_schema'
        assert 'output_format' not in request and request['betas'] == []
        assert 'temperature' not in request
        assert request['thinking'] == {'type': 'between_tools'}
        return Message(id='fixture', model=request['model'], role='assistant', type='message',
            stop_reason='end_turn', content=[ThinkingBlock(type='thinking', thinking='fixture', signature='fixture'), TextBlock(type='text', text='{"kind": "park"}')],
            usage=Usage(input_tokens=2000, output_tokens=100))
    monkeypatch.setattr('langchain_anthropic.ChatAnthropic._acreate', dispatch)
    result = await generate(LLMStructuredGenerateParams.model_validate({
        'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': 'Read the form'}]}],
        'response_format': {'type': 'json_schema', 'name': 'Decision', 'schema': {
            'type': 'object', 'properties': {'kind': {'type': 'string'}}, 'required': ['kind'],
        }},
    }))
    assert result.model_dump()['structured_content'] == {'kind': 'park'}
    assert result.usage.total_tokens == 2100
    assert Ledger(model.budget_ledger_path).snapshot()['committed_microusd'] == 5000


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['sync', 'async', 'stagehand'])
async def test_actual_sdk_transport_serializes_ga_output_and_settles(model, monkeypatch, path):
    """Exercise LangChain and the installed SDK, mocking only HTTP transport."""
    import json
    import httpx
    from anthropic import Anthropic, AsyncAnthropic
    from stagehand import LLMStructuredGenerateParams
    from backend.browser.stagehand_model import generate

    requests = []
    def respond(request):
        requests.append(request)
        body = json.loads(request.content)
        assert body['model'] == 'claude-sonnet-5-5'
        assert body['max_tokens'] == 8192
        assert body['output_config']['format']['type'] == 'json_schema'
        wire_schema = body['output_config']['format']['schema']
        assert wire_schema['properties']['kind']['type'] == 'string'
        assert wire_schema['required'] == ['kind']
        assert wire_schema['additionalProperties'] is False
        assert body['output_config']['effort'] == 'medium'
        assert body['thinking'] == {'type': 'between_tools'}
        assert body['service_tier'] == 'standard_only'
        assert not {'output_format', 'temperature', 'tools', 'tool_choice', 'betas'} & body.keys()
        # The installed SDK's beta writer supports the GA output_config shape;
        # no feature beta is enabled by selecting that writer.
        assert request.headers.get('anthropic-beta', '') == ''
        assert Ledger(model.budget_ledger_path).snapshot()['committed_microusd'] == 2_081_920
        return httpx.Response(200, json={
            'id': 'transport_fixture', 'type': 'message', 'role': 'assistant',
            'model': body['model'], 'stop_reason': 'end_turn', 'stop_sequence': None,
            'content': [{'type': 'thinking', 'thinking': 'fixture', 'signature': 'fixture'},
                        {'type': 'text', 'text': '{"kind":"park"}'}],
            'usage': {'input_tokens': 2000, 'output_tokens': 100},
        })

    sync = Anthropic(api_key='offline', max_retries=0,
                     http_client=httpx.Client(transport=httpx.MockTransport(respond)))
    async_client = AsyncAnthropic(api_key='offline', max_retries=0,
                     http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(BudgetChatAnthropic, '_client', property(lambda self: sync))
    monkeypatch.setattr(BudgetChatAnthropic, '_async_client', property(lambda self: async_client))
    schema = {'title': 'Decision', 'type': 'object',
              'properties': {'kind': {'type': 'string'}}, 'required': ['kind']}
    try:
        if path == 'stagehand':
            result = await generate(LLMStructuredGenerateParams.model_validate({
                'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': 'Read form'}]}],
                'response_format': {'type': 'json_schema', 'name': 'Decision', 'schema': schema},
            }))
            assert result.model_dump()['structured_content'] == {'kind': 'park'}
            assert result.usage.total_tokens == 2100
        else:
            chain = model.with_structured_output(schema, include_raw=True)
            result = chain.invoke('Read form') if path == 'sync' else await chain.ainvoke('Read form')
            assert result['parsed'] == {'kind': 'park'}
            assert result['raw'].usage_metadata['total_tokens'] == 2100
        assert len(requests) == 1
        assert Ledger(model.budget_ledger_path).snapshot()['committed_microusd'] == 5000
    finally:
        sync.close()
        await async_client.close()


@pytest.fixture(autouse=True)
def _explicit_owner_model_scope(monkeypatch):
    """These provider/ledger tests execute as the configured server owner."""
    from backend.shared import model_access, llm
    monkeypatch.setattr(model_access, 'get_settings', lambda: llm.get_settings())
    monkeypatch.setattr(model_access, 'is_server_model_owner', lambda uid: uid == 'test-model-owner')
    with model_access.model_user_scope('test-model-owner'):
        yield
