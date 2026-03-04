"""Verification Agent -- confirms application submissions were successful."""

from __future__ import annotations

import json
import logging
from typing import List

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from backend.orchestrator.pipeline.state import JobHunterState
from backend.shared.config import get_settings
from backend.shared.models.schemas import ApplicationResult

logger = logging.getLogger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"


def _build_llm() -> ChatAnthropic:
    settings = get_settings()
    return ChatAnthropic(
        model=HAIKU_MODEL,
        api_key=settings.ANTHROPIC_API_KEY,
        max_tokens=1024,
        temperature=0.0,
    )


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

VERIFY_SYSTEM = """\
You are a verification assistant. You are given a list of job application
results. For each application, determine whether it was successfully submitted.

In Phase 1 the only signal is the `status` field.  An application is verified
if status == "submitted".

Return ONLY valid JSON with this schema (no markdown fences):
{
  "verified_count": <int>,
  "failed_count": <int>,
  "details": [
    {
      "job_id": "<id>",
      "verified": <bool>,
      "reason": "<short explanation>"
    }
  ],
  "summary": "<one-sentence overall summary>"
}
"""


# ---------------------------------------------------------------------------
# Public agent entry point
# ---------------------------------------------------------------------------

async def run_verification_agent(state: JobHunterState) -> dict:
    """Verify that submitted applications were successful.

    In Phase 1 this checks the ``ApplicationResult.status`` field.
    Phase 2 will incorporate screenshot analysis and confirmation-page
    detection.

    Returns
    -------
    dict
        Keys: agent_statuses, errors
    """
    errors: List[str] = []

    try:
        submitted: List[ApplicationResult] = state.get("applications_submitted", [])

        if not submitted:
            return {
                "agent_statuses": {
                    "verification": "completed -- no applications to verify"
                },
                "errors": [],
            }

        # Build a lightweight payload for the LLM
        applications_data = []
        for app in submitted:
            applications_data.append(
                {
                    "job_id": app.job_id,
                    "status": app.status.value if hasattr(app.status, "value") else str(app.status),
                    "screenshot_url": app.screenshot_url,
                    "error_message": app.error_message,
                }
            )

        llm = _build_llm()

        messages = [
            SystemMessage(content=VERIFY_SYSTEM),
            HumanMessage(
                content=(
                    "## Applications to Verify\n"
                    f"```json\n{json.dumps(applications_data, indent=2)}\n```"
                )
            ),
        ]

        response = await llm.ainvoke(messages)
        verification_result = json.loads(response.content)

        summary = verification_result.get("summary", "Verification complete.")
        verified_count = verification_result.get("verified_count", 0)
        failed_count = verification_result.get("failed_count", 0)

        agent_status = (
            f"completed -- {verified_count} verified, "
            f"{failed_count} failed. {summary}"
        )

        logger.info(
            "Verification complete: %d verified, %d failed",
            verified_count,
            failed_count,
        )

    except Exception as exc:
        logger.exception("Verification agent failed")
        errors.append(f"Verification agent error: {exc}")
        agent_status = f"failed -- {exc}"

    return {
        "agent_statuses": {"verification": agent_status},
        "errors": errors,
    }


# Alias for graph.py compatibility
run = run_verification_agent
