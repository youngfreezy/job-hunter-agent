from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage
from stagehand import LLMStructuredGenerateParams

from backend.browser import stagehand_model


@pytest.mark.asyncio
async def test_model_callback_preserves_schema_images_and_usage(monkeypatch):
    params = LLMStructuredGenerateParams.model_validate({
        "system_prompt": "Only use supplied facts", "temperature": 0.0,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "Read this form"},
            {"type": "image", "mime_type": "image/png", "data": "YWJj"},
        ]}],
        "response_format": {"type": "json_schema", "name": "Decision", "schema": {
            "type": "object", "properties": {"kind": {"type": "string"}}, "required": ["kind"],
        }},
    })
    llm = MagicMock()
    llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value={
        "parsed": {"kind": "park"}, "parsing_error": None,
        "raw": AIMessage(content="", usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}),
    })
    monkeypatch.setattr(stagehand_model, "build_llm", lambda **_: llm)
    result = await stagehand_model.generate(params)
    schema = llm.with_structured_output.call_args.args[0]
    assert schema["properties"]["kind"]["type"] == "string"
    messages = llm.with_structured_output.return_value.ainvoke.await_args.args[0]
    assert messages[0].content == "Only use supplied facts"
    assert messages[1].content[1]["image_url"]["url"] == "data:image/png;base64,YWJj"
    assert result.model_dump()["structured_content"] == {"kind": "park"}
    assert result.usage.total_tokens == 120


@pytest.mark.asyncio
async def test_model_callback_does_not_invent_output_on_parse_failure(monkeypatch):
    params = LLMStructuredGenerateParams.model_validate({
        "messages": [], "response_format": {"type": "json_schema", "name": "Decision", "schema": {"type": "object"}},
    })
    llm = MagicMock()
    llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value={
        "parsed": None, "parsing_error": ValueError("invalid output"), "raw": AIMessage(content="bad"),
    })
    monkeypatch.setattr(stagehand_model, "build_llm", lambda **_: llm)
    with pytest.raises(ValueError, match="valid structured"):
        await stagehand_model.generate(params)

@pytest.mark.asyncio
@pytest.mark.parametrize('during_invoke', [False, True])
async def test_budget_callback_emits_only_stable_safe_rpc_message(monkeypatch, during_invoke):
    from backend.shared.model_budget import BudgetStopped
    from backend.browser.stagehand_budget import BUDGET_STOP, budget_stop_message
    from stagehand.rpc_client import RPCError
    from types import SimpleNamespace
    params = LLMStructuredGenerateParams.model_validate({
        'messages': [], 'response_format': {'type': 'json_schema', 'name': 'Decision', 'schema': {'type': 'object'}},
    })
    private_error = BudgetStopped('Sensitive provider/debug detail must not escape')
    llm = MagicMock()
    invoke = AsyncMock(side_effect=private_error)
    llm.with_structured_output.return_value.ainvoke = invoke
    build = MagicMock(return_value=llm, side_effect=None if during_invoke else private_error)
    monkeypatch.setattr(stagehand_model, 'build_llm', build)
    with pytest.raises(BudgetStopped) as caught:
        await stagehand_model.generate(params)
    assert str(caught.value) == BUDGET_STOP
    # The installed SDK serializes callback exceptions into this RPC error shape.
    rpc_error = RPCError(SimpleNamespace(code=-32603, data=None, message=str(caught.value)))
    assert budget_stop_message(rpc_error) == BUDGET_STOP
    assert build.call_count == 1
    assert invoke.await_count == int(during_invoke)


def test_only_exact_trusted_budget_rpc_messages_are_classified():
    from backend.browser.stagehand_budget import CEILING_STOP, budget_stop_message
    from backend.shared.model_budget import BudgetStopped
    from stagehand.rpc_client import RPCError
    from types import SimpleNamespace
    assert budget_stop_message(BudgetStopped(CEILING_STOP)) == CEILING_STOP
    assert budget_stop_message(RPCError(SimpleNamespace(code=-32603, data=None, message=CEILING_STOP))) == CEILING_STOP
    for error in [
        ValueError(CEILING_STOP),
        RPCError(SimpleNamespace(code=-1, data=None, message=CEILING_STOP)),
        RPCError(SimpleNamespace(code=-32603, data=None, message=CEILING_STOP + ' private text')),
        RPCError(SimpleNamespace(code=-32603, data=None, message='Element not found')),
    ]:
        assert budget_stop_message(error) is None
