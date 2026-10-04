"""Stagehand's supported LLM callback, using the app's server-side provider client.

This keeps inference off the cloud browser's residential proxy and preserves
the same provider credentials and workspace headers as the rest of the app.
https://docs.stagehand.dev/v4/configuration/models#bring-your-own-llm
"""

import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from stagehand import LLMStructuredGenerateParams, LLMStructuredGenerateResult

from backend.shared.llm import build_llm, default_model
from backend.shared.model_budget import BudgetStopped
from backend.browser.stagehand_budget import budget_stop_message


async def generate(params: LLMStructuredGenerateParams) -> LLMStructuredGenerateResult:
    try:
        return await _generate(params)
    except BudgetStopped as exc:
        # Stagehand serializes callback exceptions as RPCError(-32603). Preserve
        # a stable, sanitized reason that the application can recognize exactly.
        raise BudgetStopped(budget_stop_message(exc)) from None


async def _generate(params: LLMStructuredGenerateParams) -> LLMStructuredGenerateResult:
    if not isinstance(params, LLMStructuredGenerateParams):
        raise ValueError("Only structured Stagehand act/extract/observe requests are supported.")
    messages = [SystemMessage(content=params.system_prompt)] if params.system_prompt else []
    for message in params.messages:
        blocks = message.content if isinstance(message.content, list) else [message.content]
        content = []
        for block in blocks:
            item = block.root
            if item.type == "text":
                content.append({"type": "text", "text": item.text})
            elif item.type == "image":
                content.append({"type": "image_url", "image_url": {
                    "url": f"data:{item.mime_type};base64,{item.data}",
                }})
            else:
                raise ValueError(f"Unsupported Stagehand content type: {item.type}")
        message_type = HumanMessage if message.role.value == "user" else AIMessage
        messages.append(message_type(content=content))
    schema = params.response_format.schema_.model_dump(mode="json", by_alias=True, exclude_none=True)
    schema.setdefault("title", params.response_format.name)
    schema.setdefault("description", params.response_format.description or "Stagehand structured response")
    llm = build_llm(model=default_model(), max_tokens=8192,
                    temperature=params.temperature or 0.0, timeout=90)
    response = await llm.with_structured_output(schema, include_raw=True).ainvoke(
        messages, stop=params.stop_sequences or None,
    )
    if response.get("parsing_error") or response.get("parsed") is None:
        raise ValueError("The model did not return a valid structured Stagehand response.")
    data = response["parsed"]
    usage = response["raw"].usage_metadata or {}
    return LLMStructuredGenerateResult.model_validate({
        "role": "assistant", "output_format": "json_schema",
        "content": {"type": "text", "text": json.dumps(data)},
        "structured_content": data,
        "usage": {
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "cached_input_tokens": (usage.get("input_token_details") or {}).get("cache_read", 0),
        },
    })
