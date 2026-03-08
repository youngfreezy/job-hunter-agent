# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Verification Agent -- confirms application submissions were successful."""

from __future__ import annotations

import json
import logging
from typing import List

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from backend.orchestrator.pipeline.state import JobHunterState
from backend.shared.llm import build_llm as _shared_build_llm, invoke_with_retry, HAIKU_MODEL
from backend.shared.event_bus import emit_agent_event
from backend.shared.models.schemas import ApplicationResult

logger = logging.getLogger(__name__)


class VerificationDetail(BaseModel):
    job_id: str
    verified: bool
    reason: str


class VerificationResult(BaseModel):
    verified_count: int
    failed_count: int
    details: List[VerificationDetail] = Field(default_factory=list)
    summary: str

def _build_llm():
    return _shared_build_llm(model=HAIKU_MODEL, max_tokens=1024, temperature=0.0)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

VERIFY_SYSTEM = """\
You are a verification assistant. You are given a list of job application
results. For each application, determine whether it was successfully submitted.

In Phase 1 the only signal is the `status` field.  An application is verified
if status == "submitted".
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

    session_id = state.get("session_id", "")

    try:
        submitted: List[ApplicationResult] = state.get("applications_submitted", [])

        if not submitted:
            return {
                "agent_statuses": {
                    "verification": "completed -- no applications to verify"
                },
                "errors": [],
            }

        await emit_agent_event(session_id, "verification_progress", {
            "step": f"Checking {len(submitted)} submitted {'application' if len(submitted) == 1 else 'applications'}...",
            "progress": 0,
            "current": 0,
            "total": len(submitted),
        })

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

        await emit_agent_event(session_id, "verification_progress", {
            "step": "Analyzing submission confirmations...",
            "progress": 30,
            "current": 1,
            "total": 3,
        })

        llm = _build_llm()
        structured_llm = llm.with_structured_output(VerificationResult)

        messages = [
            SystemMessage(content=VERIFY_SYSTEM),
            HumanMessage(
                content=(
                    "## Applications to Verify\n"
                    f"```json\n{json.dumps(applications_data, indent=2)}\n```"
                )
            ),
        ]

        verification_result: VerificationResult = await invoke_with_retry(structured_llm, messages)

        summary = verification_result.summary
        verified_count = verification_result.verified_count
        failed_count = verification_result.failed_count

        agent_status = (
            f"completed -- {verified_count} verified, "
            f"{failed_count} failed. {summary}"
        )

        logger.info(
            "Verification complete: %d verified, %d failed",
            verified_count,
            failed_count,
        )

        await emit_agent_event(session_id, "verification_progress", {
            "step": f"Done — {verified_count} confirmed, {failed_count} need attention",
            "progress": 100,
            "current": len(submitted),
            "total": len(submitted),
        })

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
