# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""LLM-backed workflow steering judge.

Reads the current workflow state plus recent events and turns a user chat
message into:
1. A useful conversational response.
2. Structured control directives for the running workflow.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from backend.shared.llm import build_llm, default_model, invoke_with_retry

logger = logging.getLogger(__name__)


class SteeringDirective(BaseModel):
    """Single workflow control directive chosen by the judge."""

    action: Literal[
        "none",
        "pause",
        "resume_workflow",
        "skip_next_job",
        "resume_intervention",
        "confirm_login",
        "set_mode",
    ] = "none"
    mode: Literal["status"] | None = None
    reason: str = ""


class SteeringJudgeResult(BaseModel):
    """Structured judge output."""

    response_message: str = Field(
        description="Short conversational reply for the chat UI."
    )
    directives: List[SteeringDirective] = Field(default_factory=list)


_SYSTEM_PROMPT = """\
You are the workflow steering judge for an autonomous job-application system.

Your job is to supervise the entire workflow, interpret the operator's chat
message in context, and decide whether the workflow should change behavior.

You are given:
- The current workflow/session state.
- Recent workflow events.
- The latest user message.

Rules:
- Be precise and operational.
- If the user asks what is happening, answer from the current workflow state.
- If the user asks for a control change, emit structured directives.
- Only emit directives when the user intent is clear.
- If the workflow is blocked on login or captcha and the user asks to continue,
  prefer `resume_intervention` or `confirm_login` when appropriate.
- If the workflow is paused and the user asks to continue, prefer
  `resume_workflow`.
- Use `set_mode` when the user explicitly asks to switch to screenshot or
  takeover mode.
- Keep `response_message` concise, high-signal, and grounded in the session.

Response style:
- Status/explanation responses should begin with `Right now I'm ...`
- Control responses should begin with one of:
  - `I'll pause the workflow.`
  - `I'll resume the workflow.`
  - `I'll skip the next job.`
  - `I'll resume from the current intervention point.`
  - `I'll mark login as complete and continue.`
  - `I'll switch the session to ... mode.`
- If the user is ambiguous, ask a short clarifying question and emit no
  control directive.
"""


async def judge(
    *,
    user_message: str,
    session_snapshot: Dict[str, Any],
    recent_events: List[Dict[str, Any]],
) -> SteeringJudgeResult:
    """Return a conversational steering judgment for a live session."""
    llm = build_llm(model=default_model(), max_tokens=3000, temperature=0.0)
    structured_llm = llm.with_structured_output(SteeringJudgeResult)

    payload = {
        "user_message": user_message,
        "session_snapshot": session_snapshot,
        "recent_events": recent_events[-10:],
    }

    result: SteeringJudgeResult = await invoke_with_retry(
        structured_llm,
        [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=json.dumps(payload, indent=2, default=str)),
        ],
    )
    logger.info(
        "Steering judge produced %d directives for message=%r",
        len(result.directives),
        user_message[:120],
    )
    return result
