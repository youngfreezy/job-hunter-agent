"""LangGraph state definition for the JobHunter Agent pipeline."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Literal, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from typing_extensions import TypedDict

from backend.shared.models.schemas import (
    ApplicationResult,
    CoachOutput,
    JobListing,
    ScoredJob,
    SearchConfig,
    SessionSummary,
    TailoredResume,
)


def _merge_dicts(a: Dict, b: Dict) -> Dict:
    """Shallow merge for parallel agent status updates."""
    return {**a, **b}


def _last_value(a: str, b: str) -> str:
    """Last-write-wins reducer for fields set by parallel nodes."""
    return b


class JobHunterState(TypedDict):
    """Full state for the JobHunter Agent pipeline.

    Uses LangGraph reducer annotations for parallel fan-out:
    - operator.add: concatenates lists from parallel agents
    - _merge_dicts: merges dicts without overwriting
    - add_messages: LangGraph message accumulation
    """

    # --- Session identity ---
    session_id: str
    user_id: str
    created_at: str

    # --- User inputs (keyword-driven, industry-agnostic) ---
    keywords: List[str]
    locations: List[str]
    remote_only: bool
    salary_min: Optional[int]
    resume_text: str
    resume_file_path: Optional[str]
    linkedin_url: Optional[str]
    preferences: Dict[str, Any]

    # --- Intake output ---
    search_config: Optional[SearchConfig]

    # --- Career Coach output ---
    coach_output: Optional[CoachOutput]
    coached_resume: Optional[str]  # The rewritten resume text
    cover_letter_template: Optional[str]

    # --- Discovery results (fan-out: each board appends) ---
    discovered_jobs: Annotated[List[JobListing], operator.add]

    # --- Scoring results ---
    scored_jobs: List[ScoredJob]

    # --- Resume tailoring ---
    tailored_resumes: Dict[str, TailoredResume]  # job_id -> tailored resume
    resume_scores: Dict[str, int]  # job_id -> fit score

    # --- Application progress ---
    application_queue: List[str]  # job_ids approved for application
    current_application: Optional[str]
    applications_submitted: Annotated[List[ApplicationResult], operator.add]
    applications_failed: Annotated[List[ApplicationResult], operator.add]
    applications_skipped: Annotated[List[str], operator.add]

    # --- Browser state ---
    browser_session_id: Optional[str]
    current_page_url: Optional[str]

    # --- Agent statuses (parallel merge) ---
    agent_statuses: Annotated[Dict[str, str], _merge_dicts]

    # --- HITL + Steering ---
    # Annotated with _last_value so parallel fan-out nodes (discovery)
    # can each set status without conflicting.
    status: Annotated[str, _last_value]
    human_messages: Annotated[List[str], operator.add]
    steering_mode: Literal["status", "screenshot", "takeover"]

    # --- LangGraph messages ---
    messages: Annotated[List[BaseMessage], add_messages]

    # --- Errors + circuit breaker ---
    errors: Annotated[List[str], operator.add]
    consecutive_failures: int

    # --- Reporting ---
    session_summary: Optional[SessionSummary]

    # --- Billing ---
    session_start_time: Optional[str]
    applications_used: int
