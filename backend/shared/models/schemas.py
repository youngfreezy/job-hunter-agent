"""Pydantic models for the JobHunter Agent platform."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# --- Enums ---

class SessionStatus(str, Enum):
    INTAKE = "intake"
    COACHING = "coaching"
    DISCOVERING = "discovering"
    SCORING = "scoring"
    TAILORING = "tailoring"
    AWAITING_REVIEW = "awaiting_review"
    APPLYING = "applying"
    PAUSED = "paused"
    TAKEOVER = "takeover"
    COMPLETED = "completed"
    FAILED = "failed"


class SteeringMode(str, Enum):
    STATUS = "status"
    SCREENSHOT = "screenshot"
    TAKEOVER = "takeover"


class ApplicationStatus(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    FAILED = "failed"
    SKIPPED = "skipped"


class JobBoard(str, Enum):
    INDEED = "indeed"
    LINKEDIN = "linkedin"
    GLASSDOOR = "glassdoor"
    ZIPRECRUITER = "ziprecruiter"
    GOOGLE_JOBS = "google_jobs"


class ATSType(str, Enum):
    WORKDAY = "workday"
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ICIMS = "icims"
    TALEO = "taleo"
    UNKNOWN = "unknown"


# --- Request/Response Models ---

class SearchConfig(BaseModel):
    """Structured output from the Intake Agent."""
    keywords: List[str]
    locations: List[str]
    remote_only: bool = False
    salary_min: Optional[int] = None
    experience_level: Optional[str] = None  # "entry", "mid", "senior", "executive"
    job_type: Optional[str] = None  # "full-time", "contract", "part-time"
    company_size: Optional[str] = None  # "startup", "mid", "enterprise"
    exclude_companies: List[str] = Field(default_factory=list)


class JobListing(BaseModel):
    """A discovered job listing."""
    id: str
    title: str
    company: str
    location: str
    url: str
    board: JobBoard
    ats_type: ATSType = ATSType.UNKNOWN
    salary_range: Optional[str] = None
    description_snippet: Optional[str] = None
    posted_date: Optional[str] = None
    is_remote: bool = False
    is_easy_apply: bool = False
    discovered_at: datetime = Field(default_factory=datetime.utcnow)


class ScoredJob(BaseModel):
    """A job with a fit score."""
    job: JobListing
    score: int = Field(ge=0, le=100)
    score_breakdown: Dict[str, int] = Field(default_factory=dict)
    # e.g. {"keyword_match": 85, "location_match": 100, "salary_match": 70}
    reasons: List[str] = Field(default_factory=list)


class TailoredResume(BaseModel):
    """A resume tailored for a specific job."""
    job_id: str
    original_text: str
    tailored_text: str
    fit_score: int = Field(ge=0, le=100)
    changes_made: List[str] = Field(default_factory=list)


class CoverLetter(BaseModel):
    """A cover letter generated for a specific job."""
    job_id: str
    text: str
    tone: str = "professional"


class ApplicationResult(BaseModel):
    """Result of an application attempt."""
    job_id: str
    status: ApplicationStatus
    screenshot_url: Optional[str] = None
    error_message: Optional[str] = None
    cover_letter_used: Optional[str] = None
    duration_seconds: Optional[int] = None
    submitted_at: Optional[datetime] = None


class ResumeScore(BaseModel):
    """Resume quality score from the Career Coach."""
    overall: int = Field(ge=0, le=100)
    keyword_density: int = Field(ge=0, le=100)
    impact_metrics: int = Field(ge=0, le=100)
    ats_compatibility: int = Field(ge=0, le=100)
    readability: int = Field(ge=0, le=100)
    formatting: int = Field(ge=0, le=100)
    feedback: List[str] = Field(default_factory=list)


class CoachOutput(BaseModel):
    """Output from the Career Coach Agent."""
    rewritten_resume: str
    resume_score: ResumeScore
    cover_letter_template: str
    linkedin_advice: List[str] = Field(default_factory=list)
    confidence_message: str  # Impostor syndrome coaching message
    key_strengths: List[str] = Field(default_factory=list)
    improvement_areas: List[str] = Field(default_factory=list)


class SessionSummary(BaseModel):
    """Session summary from the Reporting Agent."""
    session_id: str
    total_discovered: int
    total_scored: int
    total_applied: int
    total_failed: int
    total_skipped: int
    top_companies: List[str]
    avg_fit_score: float
    resume_score: Optional[ResumeScore] = None
    duration_minutes: int
    next_steps: List[str] = Field(default_factory=list)


# --- SSE Event Models ---

class SSEEvent(BaseModel):
    """Server-Sent Event payload."""
    type: str
    data: Dict[str, Any]


# --- API Request Models ---

class StartSessionRequest(BaseModel):
    keywords: List[str]
    locations: List[str] = Field(default_factory=lambda: ["Remote"])
    remote_only: bool = False
    salary_min: Optional[int] = None
    resume_text: Optional[str] = None
    linkedin_url: Optional[str] = None
    preferences: Dict[str, Any] = Field(default_factory=dict)


class SteerRequest(BaseModel):
    """User steering command via chat."""
    message: str
    mode: Optional[SteeringMode] = None


class ReviewRequest(BaseModel):
    """User approval/rejection of shortlist."""
    approved_job_ids: List[str]
    feedback: Optional[str] = None
