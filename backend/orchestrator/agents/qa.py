# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""QA Agent -- analyses application results and gates backfill decisions.

Runs after verification to assess:
1. Success rate and error distribution
2. Failure patterns (e.g. all LinkedIn jobs hit auth walls)
3. Boards to skip in backfill rounds
4. Retryable vs non-retryable failures
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from backend.orchestrator.pipeline.state import JobHunterState
from backend.shared.llm import build_llm as _shared_build_llm, invoke_with_retry, HAIKU_MODEL
from backend.shared.event_bus import emit_agent_event

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structured output models
# ---------------------------------------------------------------------------

class QAIssue(BaseModel):
    category: str = Field(description="Issue type: high_failure_rate, auth_wall_pattern, low_diversity, timeout_cluster")
    severity: Literal["warning", "critical"] = "warning"
    detail: str = ""


class QADecision(BaseModel):
    decision: Literal["continue", "halt"] = Field(
        description="continue = proceed with backfill if needed, halt = stop the pipeline"
    )
    reasoning: str = ""
    issues: List[QAIssue] = Field(default_factory=list)
    boards_to_skip: List[str] = Field(default_factory=list, description="Board names to exclude from backfill discovery")
    retryable_job_ids: List[str] = Field(default_factory=list, description="Job IDs worth retrying")


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

QA_SYSTEM = """\
You are a quality assurance agent for a job application automation system.

Given a summary of application attempts (submitted, failed, skipped), assess
the results and produce a structured QA decision.

Rules:
- If >60% of failures on a specific board are "auth_required", add that board
  to boards_to_skip (the user hasn't provided credentials for it).
- If the overall success rate is 0% and total attempts >= 5, set decision=halt.
- Jobs that failed with "timeout" or "form_navigation" are retryable.
- Jobs that failed with "auth_required", "job_expired", "duplicate", or
  "credit_insufficient" are NOT retryable.
- Keep reasoning concise (1-2 sentences).
"""


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _build_llm():
    return _shared_build_llm(model=HAIKU_MODEL, max_tokens=1024, temperature=0.0)


def _summarise_results(state: JobHunterState) -> Dict[str, Any]:
    """Build a lightweight summary dict for the LLM."""
    submitted = state.get("applications_submitted") or []
    failed = state.get("applications_failed") or []
    skipped = state.get("applications_skipped") or []

    total = len(submitted) + len(failed) + len(skipped)

    # Error category breakdown
    error_categories: Dict[str, int] = {}
    board_errors: Dict[str, Dict[str, int]] = {}  # board -> {category -> count}
    failed_job_details: List[Dict[str, str]] = []

    for app in failed:
        cat = str(getattr(app, "error_category", None) or app.error_message or "unknown")
        error_categories[cat] = error_categories.get(cat, 0) + 1

        # Track per-board errors
        board = getattr(app, "ats_type", None) or "unknown"
        if board not in board_errors:
            board_errors[board] = {}
        board_errors[board][cat] = board_errors[board].get(cat, 0) + 1

        failed_job_details.append({
            "job_id": app.job_id,
            "error": cat,
            "board": board,
        })

    return {
        "total_attempts": total,
        "submitted": len(submitted),
        "failed": len(failed),
        "skipped": len(skipped),
        "success_rate_pct": round(100 * len(submitted) / total, 1) if total > 0 else 0,
        "error_categories": error_categories,
        "board_errors": board_errors,
        "failed_jobs": failed_job_details[:20],  # Cap for token budget
        "backfill_round": state.get("backfill_rounds", 0),
    }


async def run_qa_agent(state: JobHunterState) -> dict:
    """Analyse application results and produce a QA decision.

    Returns
    -------
    dict
        Keys: qa_analysis, agent_statuses, errors
    """
    errors: List[str] = []
    session_id = state.get("session_id", "")

    try:
        summary = _summarise_results(state)

        if summary["total_attempts"] == 0:
            qa_decision = QADecision(
                decision="halt",
                reasoning="No applications were attempted.",
            )
        else:
            await emit_agent_event(session_id, "qa_progress", {
                "step": f"Analysing {summary['total_attempts']} application results...",
                "progress": 0,
            })

            llm = _build_llm()
            structured_llm = llm.with_structured_output(QADecision)

            messages = [
                SystemMessage(content=QA_SYSTEM),
                HumanMessage(content=(
                    "## Application Results Summary\n"
                    f"```json\n{json.dumps(summary, indent=2)}\n```\n\n"
                    "Produce a QA decision."
                )),
            ]

            qa_decision = await invoke_with_retry(structured_llm, messages)

            await emit_agent_event(session_id, "qa_progress", {
                "step": f"QA: {qa_decision.decision} — {qa_decision.reasoning}",
                "progress": 100,
                "decision": qa_decision.decision,
                "boards_to_skip": qa_decision.boards_to_skip,
            })

        logger.info(
            "QA agent: decision=%s, issues=%d, boards_to_skip=%s",
            qa_decision.decision,
            len(qa_decision.issues),
            qa_decision.boards_to_skip,
        )

    except Exception as exc:
        logger.exception("QA agent failed")
        errors.append(f"QA agent error: {exc}")
        qa_decision = QADecision(
            decision="continue",
            reasoning=f"QA analysis failed ({exc}), defaulting to continue.",
        )

    return {
        "qa_analysis": qa_decision.model_dump(),
        "agent_statuses": {"qa": f"completed — {qa_decision.decision}"},
        "errors": errors,
    }


# Alias for graph.py compatibility
run = run_qa_agent
