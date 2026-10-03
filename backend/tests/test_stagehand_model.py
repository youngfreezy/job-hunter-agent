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
