"""Interactive coach-chat loop for revising coached artifacts before approval."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from backend.shared.llm import build_llm, premium_model, invoke_with_retry
from backend.shared.models.schemas import CoachOutput

logger = logging.getLogger(__name__)


class CoachChatResult(BaseModel):
    """Structured result for an iterative coach revision turn."""

    response_message: str = Field(
        description="Short conversational reply that explains what changed."
    )
    coach_output: CoachOutput


_SYSTEM_PROMPT = """\
You are the interactive Career Coach for a job application workflow.

You will receive:
- the user's original resume
- the current coached output
- prior coach chat turns
- the latest user request

Your task:
1. Revise the coached output to satisfy the user's latest request.
2. Keep all changes factually grounded in the original resume and prior coached output.
3. Preserve structure and usefulness. Do not erase good content unless the user asks.
4. If the user asks for a direct text edit, comply as literally as possible.
5. If the request is ambiguous, make the smallest reasonable revision and explain it.

Return JSON with:
- response_message: concise, operational, and clear
- coach_output: the full updated CoachOutput object
"""


async def revise_coach_output(
    *,
    original_resume: str,
    current_output: CoachOutput,
    latest_user_message: str,
    chat_history: List[Dict[str, str]],
) -> CoachChatResult:
    """Revise the current coached artifacts in response to user feedback."""
    llm = build_llm(
        model=premium_model(),
        max_tokens=3500,
        temperature=0.0,
        timeout=180,
    ).with_structured_output(CoachChatResult)

    payload = {
        "original_resume": original_resume,
        "current_output": current_output.model_dump(),
        "chat_history": chat_history[-8:],
        "latest_user_message": latest_user_message,
    }

    result: CoachChatResult = await invoke_with_retry(
        llm,
        [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=json.dumps(payload, indent=2)),
        ],
    )
    logger.info("Coach chat revised coached output for request=%r", latest_user_message[:120])
    return result
