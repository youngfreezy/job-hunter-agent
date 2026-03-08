"""LangGraph graph definition for the Interview Prep Agent."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict

from langgraph.graph import END, START, StateGraph

from backend.orchestrator.interview_prep.state import InterviewPrepState

logger = logging.getLogger(__name__)


async def company_research_node(state: InterviewPrepState) -> Dict[str, Any]:
    """Research the company and generate a brief."""
    from backend.shared.llm import build_llm, default_model, invoke_with_retry
    from langchain_core.messages import HumanMessage, SystemMessage

    company = state.get("company", "")
    role = state.get("role", "")
    job_desc = state.get("job_description", "")

    llm = build_llm(model=default_model(), max_tokens=2048, temperature=0.0)

    messages = [
        SystemMessage(content="""You are a company research analyst preparing a candidate for an interview.
Generate a company brief with:
1. Company mission/what they do
2. Culture signals (from public info)
3. Recent news/developments
4. Key things the candidate should mention based on the job description

Return as JSON:
{
  "mission": "...",
  "culture": "...",
  "recent_news": "...",
  "glassdoor_rating": null,
  "things_to_mention": ["...", "..."],
  "interview_tips": ["...", "..."]
}"""),
        HumanMessage(content=f"Company: {company}\nRole: {role}\nJob Description: {job_desc}"),
    ]

    response = await invoke_with_retry(llm, messages)
    import json
    try:
        brief = json.loads(response.content)
    except (json.JSONDecodeError, AttributeError):
        brief = {"mission": "", "culture": "", "recent_news": "", "things_to_mention": [], "interview_tips": []}

    return {
        "company_brief": brief,
        "status": "researching_company",
    }


async def question_generator_node(state: InterviewPrepState) -> Dict[str, Any]:
    """Generate interview questions based on role and company."""
    from backend.shared.llm import build_llm, default_model, invoke_with_retry
    from langchain_core.messages import HumanMessage, SystemMessage

    company = state.get("company", "")
    role = state.get("role", "")
    job_desc = state.get("job_description", "")
    resume = state.get("resume_text", "")

    llm = build_llm(model=default_model(), max_tokens=4096, temperature=0.3)

    messages = [
        SystemMessage(content="""You are an expert interview coach. Generate 15 interview questions for this specific role and company.

Include a mix of:
- 4 behavioral questions (STAR format expected)
- 4 technical questions (role-specific)
- 4 situational questions (hypothetical scenarios)
- 3 culture fit questions (company values)

Return as JSON:
{
  "questions": [
    {"id": "q1", "category": "behavioral", "question": "...", "source": "ai_generated"},
    ...
  ]
}"""),
        HumanMessage(content=f"Company: {company}\nRole: {role}\nJob Description: {job_desc}\nCandidate Resume: {resume[:1000]}"),
    ]

    response = await invoke_with_retry(llm, messages)
    import json
    try:
        parsed = json.loads(response.content)
        questions = parsed.get("questions", [])
    except (json.JSONDecodeError, AttributeError):
        questions = []

    # Ensure IDs
    for i, q in enumerate(questions):
        if not q.get("id"):
            q["id"] = f"q{i+1}"
        if not q.get("source"):
            q["source"] = "ai_generated"

    return {
        "questions": questions,
        "status": "generating_questions",
    }


async def prep_report_node(state: InterviewPrepState) -> Dict[str, Any]:
    """Generate the final readiness report from all grades."""
    grades = state.get("grades", [])
    if not grades:
        return {"overall_readiness": 0.0, "status": "completed"}

    # Calculate category scores
    category_totals: Dict[str, list] = {}
    for grade in grades:
        # Find the question category
        q_id = grade.get("question_id", "")
        questions = state.get("questions", [])
        category = "unknown"
        for q in questions:
            if q.get("id") == q_id:
                category = q.get("category", "unknown")
                break
        category_totals.setdefault(category, []).append(grade.get("overall", 5))

    category_scores = {cat: sum(scores) / len(scores) for cat, scores in category_totals.items()}
    overall = sum(g.get("overall", 5) for g in grades) / len(grades)

    return {
        "overall_readiness": round(overall, 1),
        "category_scores": {k: round(v, 1) for k, v in category_scores.items()},
        "status": "completed",
    }


def build_interview_prep_graph(checkpointer=None):
    """Build the Interview Prep StateGraph."""
    g = StateGraph(InterviewPrepState)

    g.add_node("company_research", company_research_node)
    g.add_node("question_generator", question_generator_node)
    g.add_node("prep_report", prep_report_node)

    g.add_edge(START, "company_research")
    g.add_edge("company_research", "question_generator")
    g.add_edge("question_generator", END)  # Pauses here — user answers questions via API
    # prep_report is called separately after all answers are submitted

    return g.compile(checkpointer=checkpointer)
