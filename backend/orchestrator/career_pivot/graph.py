"""LangGraph graph definition for the Career Pivot Advisor."""

from __future__ import annotations

import logging
from typing import Any, Dict

from langgraph.graph import END, START, StateGraph

from backend.orchestrator.career_pivot.state import CareerPivotState

logger = logging.getLogger(__name__)


async def skill_parser_node(state: CareerPivotState) -> Dict[str, Any]:
    """Parse skills, role, experience from resume text."""
    from backend.shared.llm import build_llm, default_model, invoke_with_retry
    from langchain_core.messages import HumanMessage, SystemMessage

    resume_text = state.get("resume_text", "")

    llm = build_llm(model=default_model(), max_tokens=2048, temperature=0.0)

    messages = [
        SystemMessage(content="""You are a career analyst. Extract from the resume:
1. Current/most recent job title
2. List of all skills (technical and soft)
3. Years of experience (estimate from dates)
4. Primary industry

Return as JSON:
{"role": "...", "skills": ["..."], "years_experience": N, "industry": "..."}"""),
        HumanMessage(content=f"Resume:\n{resume_text}"),
    ]

    response = await invoke_with_retry(llm, messages)
    import json
    try:
        parsed = json.loads(response.content)
    except (json.JSONDecodeError, AttributeError):
        parsed = {"role": "Unknown", "skills": [], "years_experience": 0, "industry": "Unknown"}

    return {
        "parsed_role": parsed.get("role", "Unknown"),
        "parsed_skills": parsed.get("skills", []),
        "years_experience": parsed.get("years_experience", 0),
        "industry": parsed.get("industry", "Unknown"),
        "status": "parsing_skills",
    }


async def risk_assessor_node(state: CareerPivotState) -> Dict[str, Any]:
    """Assess automation risk for the user's current role."""
    from backend.shared.llm import build_llm, default_model, invoke_with_retry
    from langchain_core.messages import HumanMessage, SystemMessage

    role = state.get("parsed_role", "Unknown")
    skills = state.get("parsed_skills", [])
    industry = state.get("industry", "Unknown")

    llm = build_llm(model=default_model(), max_tokens=2048, temperature=0.0)

    messages = [
        SystemMessage(content="""You are an AI automation risk analyst using O*NET and McKinsey data.
For the given role, assess:
1. Overall automation risk percentage (0-100)
2. Task-by-task breakdown with risk percentages

Return as JSON:
{
  "automation_risk_score": 72.5,
  "task_breakdown": [
    {"task": "Campaign reporting", "risk_pct": 92},
    {"task": "Strategy planning", "risk_pct": 23}
  ]
}

Base your assessment on real O*NET automation susceptibility data. Be specific to the role and industry."""),
        HumanMessage(content=f"Role: {role}\nIndustry: {industry}\nSkills: {', '.join(skills)}"),
    ]

    response = await invoke_with_retry(llm, messages)
    import json
    try:
        parsed = json.loads(response.content)
    except (json.JSONDecodeError, AttributeError):
        parsed = {"automation_risk_score": 50.0, "task_breakdown": []}

    return {
        "automation_risk_score": parsed.get("automation_risk_score", 50.0),
        "task_breakdown": parsed.get("task_breakdown", []),
        "status": "assessing_risk",
    }


async def role_mapper_node(state: CareerPivotState) -> Dict[str, Any]:
    """Map adjacent roles based on skill overlap."""
    from backend.shared.llm import build_llm, default_model, invoke_with_retry
    from langchain_core.messages import HumanMessage, SystemMessage

    role = state.get("parsed_role", "Unknown")
    skills = state.get("parsed_skills", [])
    years = state.get("years_experience", 0)
    industry = state.get("industry", "Unknown")
    location = state.get("location", "Remote")

    llm = build_llm(model=default_model(), max_tokens=4096, temperature=0.0)

    messages = [
        SystemMessage(content="""You are a career transition advisor using O*NET skills taxonomy and BLS data.
Find 3-5 adjacent roles that:
1. Share 60-90% skill overlap with the user's current skills
2. Have lower AI automation risk
3. Have strong job market demand
4. Offer competitive or better salary

For each role, return:
{
  "recommended_pivots": [
    {
      "role": "Product Manager",
      "skill_overlap_pct": 82.0,
      "salary_range": {"min": 95000, "max": 145000, "median": 120000},
      "market_demand": 1247,
      "ai_risk_pct": 28.0,
      "missing_skills": ["Agile certification", "SQL"],
      "learning_plan": [
        {"week": "1-2", "topic": "Agile Fundamentals", "resources": [{"name": "Coursera: Agile PM", "hours": 10, "cost": "Free"}]},
        {"week": "3-4", "topic": "SQL for PMs", "resources": [{"name": "Mode SQL Tutorial", "hours": 8, "cost": "Free"}]}
      ],
      "time_to_pivot_weeks": 6
    }
  ]
}

Be specific and realistic. Use actual O*NET occupation codes where possible."""),
        HumanMessage(content=f"Current role: {role}\nYears experience: {years}\nIndustry: {industry}\nSkills: {', '.join(skills)}\nLocation: {location}"),
    ]

    response = await invoke_with_retry(llm, messages)
    import json
    try:
        parsed = json.loads(response.content)
    except (json.JSONDecodeError, AttributeError):
        parsed = {"recommended_pivots": []}

    return {
        "recommended_pivots": parsed.get("recommended_pivots", []),
        "status": "mapping_roles",
    }


async def report_generator_node(state: CareerPivotState) -> Dict[str, Any]:
    """Generate final pivot report."""
    return {
        "report_generated": True,
        "status": "completed",
    }


def build_career_pivot_graph(checkpointer=None):
    """Build the Career Pivot Advisor StateGraph."""
    g = StateGraph(CareerPivotState)

    g.add_node("skill_parser", skill_parser_node)
    g.add_node("risk_assessor", risk_assessor_node)
    g.add_node("role_mapper", role_mapper_node)
    g.add_node("report_generator", report_generator_node)

    g.add_edge(START, "skill_parser")
    g.add_edge("skill_parser", "risk_assessor")
    g.add_edge("risk_assessor", "role_mapper")
    g.add_edge("role_mapper", "report_generator")
    g.add_edge("report_generator", END)

    return g.compile(checkpointer=checkpointer)
