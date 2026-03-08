"""LangGraph state definition for the Interview Prep Agent."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Optional

from typing_extensions import TypedDict


def _last_value(a: str, b: str) -> str:
    return b


class InterviewQuestion(TypedDict):
    """A single interview question."""
    id: str
    category: str  # behavioral, technical, situational, culture_fit
    question: str
    follow_up: Optional[str]
    source: str  # glassdoor, ai_generated


class AnswerGrade(TypedDict):
    """Grading for a single answer."""
    question_id: str
    relevance: int  # 0-10
    specificity: int  # 0-10
    star_structure: int  # 0-10
    confidence: int  # 0-10
    overall: int  # 0-10
    feedback: str
    strong_answer_example: str


class InterviewPrepState(TypedDict):
    """Full state for the Interview Prep pipeline."""

    # --- Session identity ---
    session_id: str
    user_id: str
    application_id: Optional[str]  # links to job application
    created_at: str

    # --- Context ---
    company: str
    role: str
    job_description: Optional[str]
    resume_text: str

    # --- Company Research ---
    company_brief: Optional[Dict[str, Any]]  # mission, culture, news, glassdoor_rating, tips

    # --- Questions ---
    questions: List[InterviewQuestion]
    current_question_index: int

    # --- Transcript ---
    transcript: Annotated[List[Dict[str, str]], operator.add]  # [{question, answer, grade}]

    # --- Grading ---
    grades: List[AnswerGrade]
    overall_readiness: Optional[float]
    category_scores: Optional[Dict[str, float]]  # {behavioral: 8.1, technical: 6.3, ...}

    # --- HITL ---
    waiting_for_answer: bool
    current_answer: Optional[str]

    # --- Pipeline control ---
    status: Annotated[str, _last_value]
    errors: Annotated[List[str], operator.add]
    is_free_session: bool
    questions_answered: int
    max_free_questions: int  # 7
