# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""LangGraph state definition for the Freelance/Contract Matchmaker."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Optional

from typing_extensions import TypedDict


def _last_value(a: str, b: str) -> str:
    return b


class GigListing(TypedDict):
    """A discovered freelance gig."""
    id: str
    title: str
    platform: str  # upwork, linkedin, fiverr, freelancer
    url: str
    client_name: Optional[str]
    budget_type: str  # fixed, hourly
    budget_min: Optional[float]
    budget_max: Optional[float]
    duration: Optional[str]
    description_snippet: Optional[str]
    posted_date: Optional[str]
    proposals_count: Optional[int]
    match_score: Optional[float]


class FreelanceProfile(TypedDict):
    """A platform-specific freelance profile."""
    platform: str
    bio: str
    headline: str
    hourly_rate: float
    skills_tags: List[str]
    portfolio_suggestions: List[str]


class FreelanceState(TypedDict):
    """Full state for the Freelance Matchmaker pipeline."""

    # --- Session identity ---
    session_id: str
    user_id: str
    created_at: str

    # --- User inputs ---
    resume_text: str
    hourly_rate_min: Optional[float]
    hourly_rate_max: Optional[float]
    platforms: List[str]  # ["upwork", "linkedin", "fiverr"]
    project_types: List[str]  # ["web_development", "api_integration"]
    availability: str  # "full_time", "part_time"

    # --- Profile Generation output ---
    profiles: List[FreelanceProfile]

    # --- Gig Discovery output ---
    discovered_gigs: Annotated[List[GigListing], operator.add]

    # --- Gig Scoring output ---
    scored_gigs: List[Dict[str, Any]]  # sorted by match score

    # --- Proposal Generation ---
    proposals: Dict[str, str]  # gig_id -> proposal_text
    submitted_proposals: Annotated[List[str], operator.add]  # gig_ids

    # --- HITL ---
    approved_gigs: Optional[List[str]]  # gig_ids approved for proposal submission

    # --- Analytics ---
    win_rate: Optional[float]
    total_submitted: int
    total_views: int
    total_shortlisted: int

    # --- Pipeline control ---
    status: Annotated[str, _last_value]
    errors: Annotated[List[str], operator.add]
