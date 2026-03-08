# Copyright (c) 2026 V2 Software LLC. All rights reserved.

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
    SessionConfig,
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
    search_radius: int
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
    coach_chat_history: Annotated[List[Dict[str, str]], operator.add]

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
    steering_mode: Literal["status"]
    steering_messages_processed: int
    pending_supervisor_response: Optional[str]
    pending_supervisor_directives: List[Dict[str, Any]]
    pause_requested: bool
    pause_resume_node: Optional[str]
    status_before_pause: Optional[str]
    skip_next_job_requested: bool
    pending_coach_review_input: Optional[Dict[str, Any]]
    pending_shortlist_review_input: Optional[Dict[str, Any]]

    # --- LangGraph messages ---
    messages: Annotated[List[BaseMessage], add_messages]

    # --- Errors + circuit breaker ---
    errors: Annotated[List[str], operator.add]
    consecutive_failures: int

    # --- Reporting ---
    session_summary: Optional[SessionSummary]

    # --- Session config ---
    session_config: Optional[SessionConfig]

    # --- Billing ---
    session_start_time: Optional[str]
    applications_used: int
