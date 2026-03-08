"""LangGraph state definition for the Career Pivot Advisor."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Optional

from typing_extensions import TypedDict


def _last_value(a: str, b: str) -> str:
    return b


class PivotRole(TypedDict):
    """A recommended pivot role."""
    role: str
    skill_overlap_pct: float
    salary_range: Dict[str, Any]  # {min, max, median}
    market_demand: int
    ai_risk_pct: float
    missing_skills: List[str]
    learning_plan: List[Dict[str, Any]]
    time_to_pivot_weeks: int


class CareerPivotState(TypedDict):
    """Full state for the Career Pivot Advisor pipeline."""

    # --- Session identity ---
    session_id: str
    user_id: str
    created_at: str

    # --- User inputs ---
    resume_text: str
    current_role: Optional[str]
    current_skills: List[str]
    location: Optional[str]

    # --- Skill Parser output ---
    parsed_role: Optional[str]
    parsed_skills: List[str]
    years_experience: Optional[int]
    industry: Optional[str]

    # --- Risk Assessment output ---
    automation_risk_score: Optional[float]
    task_breakdown: List[Dict[str, Any]]  # [{task, risk_pct}]

    # --- Role Mapping output ---
    recommended_pivots: List[PivotRole]

    # --- HITL ---
    selected_pivot_indices: Optional[List[int]]  # user picks which pivots to explore

    # --- Learning Plan output ---
    learning_plans: Dict[str, Any]  # role -> detailed plan

    # --- Market Validation output ---
    market_data: Dict[str, Any]  # role -> {openings, salary_range, remote_pct}

    # --- Report ---
    report_generated: bool

    # --- Pipeline control ---
    status: Annotated[str, _last_value]
    errors: Annotated[List[str], operator.add]
