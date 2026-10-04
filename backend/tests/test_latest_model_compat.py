"""Offline wire-format checks: no provider requests or browser sessions."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from backend.shared import llm


class Decision(BaseModel):
    kind: str


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.delenv('JOBHUNTER_MODEL_BUDGET_LEDGER', raising=False)
    settings = SimpleNamespace(LLM_PROVIDER='anthropic', ANTHROPIC_API_KEY='test',
        ANTHROPIC_WORKSPACE_ID='', ANTHROPIC_DEFAULT_MODEL='claude-sonnet-5-5',
        ANTHROPIC_BROWSER_MODEL='claude-sonnet-5-5', OPENAI_API_KEY='test',
        OPENAI_DEFAULT_MODEL='gpt-6-luna', OPENAI_BROWSER_MODEL='gpt-6-luna')
    monkeypatch.setattr(llm, 'get_settings', lambda: settings)
    return settings


@pytest.mark.parametrize('model', ['claude-sonnet-5-5', 'claude-opus-5-5'])
def test_latest_claude_factory_native_json_wire_format(settings, monkeypatch, model):
    from anthropic.types import Message, TextBlock, Usage
    def dispatch(self, request):
        assert request['model'] == model
        assert not {'temperature', 'top_p', 'top_k', 'tools', 'tool_choice', 'output_format'} & request.keys()
        assert request['betas'] == []
        assert request['output_config']['format']['type'] == 'json_schema'
        if model == 'claude-sonnet-5-5':
            assert request['thinking'] == {'type': 'between_tools'}
            assert request['output_config']['effort'] == 'medium'
        else:
            assert 'thinking' not in request
        return Message(id='fixture', model=model, role='assistant', type='message',
            stop_reason='end_turn', content=[TextBlock(type='text', text='{"kind":"park"}')],
            usage=Usage(input_tokens=200, output_tokens=10))
    monkeypatch.setattr('langchain_anthropic.ChatAnthropic._create', dispatch)
    assert llm.build_llm(model=model).with_structured_output(Decision).invoke('Inspect') == Decision(kind='park')


def test_haiku_preserves_legacy_structured_tool_and_temperature(settings):
    model = llm.build_llm(model='claude-haiku-4-5-20251001', temperature=0.2)
    bound = model.with_structured_output(Decision).first
    request = model._get_request_payload('Inspect', **bound.kwargs)
    assert request['temperature'] == 0.2
    assert request['tool_choice']['type'] == 'tool'
    assert 'output_config' not in request


@pytest.mark.parametrize('model', ['gpt-6-luna', 'gpt-6-astra', 'gpt-6.1-sol'])
def test_gpt6_actual_structured_payload_uses_responses(settings, model):
    settings.LLM_PROVIDER = 'openai'
    client = llm.build_llm(model=model, max_tokens=8192)
    bound = client.with_structured_output(Decision).first
    request = client._get_request_payload('Inspect', **bound.kwargs)
    assert client.use_responses_api is True
    assert request['model'] == model
    assert 'input' in request and 'messages' not in request
    assert request['reasoning']['effort'] == 'low'
    assert request['max_output_tokens'] == 8192
    assert 'temperature' not in request


@pytest.mark.asyncio
async def test_browser_use_luna_actual_chat_payload(settings, monkeypatch):
    from browser_use.llm.messages import UserMessage
    settings.LLM_PROVIDER = 'openai'
    client = llm.build_browser_use_llm()
    create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content='ready'), finish_reason='stop')], usage=None))
    monkeypatch.setattr(type(client), 'get_client', lambda self: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    await client.ainvoke([UserMessage(content='Inspect')])
    request = create.await_args.kwargs
    assert request['model'] == 'gpt-6-luna'
    assert request['reasoning_effort'] == 'none'
    assert not {'temperature', 'frequency_penalty', 'top_p'} & request.keys()


@pytest.mark.parametrize('model', ['gpt-6-astra', 'gpt-6.1-sol'])
def test_browser_use_rejects_models_requiring_responses(settings, model):
    settings.LLM_PROVIDER = 'openai'
    with pytest.raises(ValueError, match='Stagehand'):
        llm.build_browser_use_llm(model=model)


@pytest.mark.parametrize('model', ['claude-sonnet-5-5', 'claude-opus-5-5'])
def test_browser_use_latest_claude_requires_stagehand(settings, model):
    with pytest.raises(ValueError, match='Stagehand'):
        llm.build_browser_use_llm(model=model)


def test_gpt5_override_preserves_legacy_options(settings):
    settings.LLM_PROVIDER = 'openai'
    client = llm.build_llm(model='gpt-5-mini')
    assert client.use_responses_api is None
    assert client.temperature is None  # Existing LangChain GPT-5 normalization.


@pytest.fixture(autouse=True)
def _explicit_owner_model_scope(monkeypatch):
    """These provider/ledger tests execute as the configured server owner."""
    from backend.shared import model_access, llm
    monkeypatch.setattr(model_access, 'get_settings', lambda: llm.get_settings())
    monkeypatch.setattr(model_access, 'is_server_model_owner', lambda uid: uid == 'test-model-owner')
    with model_access.model_user_scope('test-model-owner'):
        yield
