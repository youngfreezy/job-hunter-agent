"""LangGraph graph definition for the Career Pivot Advisor."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict

from langgraph.graph import END, START, StateGraph

from backend.orchestrator.career_pivot.state import CareerPivotState

logger = logging.getLogger(__name__)


def _strip_json_fences(text: str) -> str:
    """Strip markdown ```json ... ``` fences from LLM output."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _extract_text(content) -> str:
    """Extract text from various LLM response content formats."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif "text" in block:
                    parts.append(block["text"])
            elif hasattr(block, "text"):
                parts.append(block.text)
            else:
                parts.append(str(block))
        return "".join(parts)
    if hasattr(content, "text"):
        return content.text
    return str(content) if content else ""


def _safe_parse_json(text, fallback: dict) -> dict:
    """Parse JSON from LLM response, stripping markdown fences first."""
    try:
        extracted = _extract_text(text)
        if not extracted.strip():
            logger.warning("Empty LLM response (raw type=%s), using fallback", type(text).__name__)
            return fallback
        cleaned = _strip_json_fences(extracted)
        # Try direct parse first (fast path for clean JSON)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        # Bracket-match to extract the outermost JSON object,
        # handling leading/trailing text or incomplete responses.
        start = cleaned.find("{")
        if start >= 0:
            depth = 0
            for i, c in enumerate(cleaned[start:], start):
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        return json.loads(cleaned[start : i + 1])
        raise json.JSONDecodeError("No complete JSON object found", cleaned, 0)
    except (json.JSONDecodeError, AttributeError, TypeError) as exc:
        logger.warning("Failed to parse LLM JSON (%s): %.300s", type(exc).__name__, repr(text))
        return fallback


async def skill_parser_node(state: CareerPivotState) -> Dict[str, Any]:
    """Parse skills, role, experience from resume text."""
    from backend.shared.llm import build_llm, default_model, invoke_with_retry
    from langchain_core.messages import HumanMessage, SystemMessage

    resume_text = state.get("resume_text", "")
    llm = build_llm(model=default_model(), max_tokens=8192, temperature=0.0)

    messages = [
        SystemMessage(content="""You are a career analyst specializing in O*NET occupational classification.

Analyze the resume and extract:

1. **O*NET SOC code and title** for the current/most recent role (e.g. "15-1252.00 Software Developers" or "11-2021.00 Marketing Managers"). Use the exact SOC code from the O*NET-SOC 2019 taxonomy.

2. **Skills** categorized by O*NET KSA taxonomy:
   - Knowledge areas (e.g. "Computers and Electronics", "Administration and Management")
   - Skills (e.g. "Programming", "Complex Problem Solving", "Critical Thinking")
   - Abilities (e.g. "Deductive Reasoning", "Written Comprehension")

3. **Years of experience** — calculate from employment dates on the resume. Return an integer, never "Unknown".

4. **Primary industry** — use BLS NAICS sector name (e.g. "Professional, Scientific, and Technical Services", "Information", "Finance and Insurance").

Return ONLY valid JSON, no markdown:
{
  "soc_code": "15-1252.00",
  "role": "Software Developer",
  "skills": ["Programming", "Complex Problem Solving", "Systems Analysis", "Critical Thinking"],
  "knowledge_areas": ["Computers and Electronics", "Mathematics", "Engineering and Technology"],
  "abilities": ["Deductive Reasoning", "Inductive Reasoning", "Written Comprehension"],
  "years_experience": 5,
  "industry": "Professional, Scientific, and Technical Services"
}"""),
        HumanMessage(content=f"Resume:\n{resume_text}"),
    ]

    response = await invoke_with_retry(llm, messages)
    parsed = _safe_parse_json(
        response.content,
        {"role": "Unknown", "skills": [], "years_experience": 0, "industry": "Unknown"},
    )

    all_skills = parsed.get("skills", [])
    all_skills.extend(parsed.get("knowledge_areas", []))
    all_skills.extend(parsed.get("abilities", []))

    return {
        "parsed_role": parsed.get("role", "Unknown"),
        "parsed_skills": all_skills,
        "years_experience": parsed.get("years_experience", 0),
        "industry": parsed.get("industry", "Unknown"),
        "soc_code": parsed.get("soc_code", ""),
        "knowledge_areas": parsed.get("knowledge_areas", []),
        "abilities": parsed.get("abilities", []),
        "status": "parsing_skills",
    }


async def _fetch_page_text(url: str) -> str:
    """Fetch a URL and return cleaned text content."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            })
            resp.raise_for_status()
            html = resp.text
            text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", url, str(exc)[:120])
        return ""


async def onet_researcher_node(state: CareerPivotState) -> Dict[str, Any]:
    """Fetch real O*NET occupation data from onetonline.org."""
    import asyncio

    soc_code = state.get("soc_code", "")
    if not soc_code:
        return {"onet_research": "", "status": "researching_onet"}

    logger.info("Fetching O*NET data for SOC %s", soc_code)

    summary_url = f"https://www.onetonline.org/link/summary/{soc_code}"
    details_url = f"https://www.onetonline.org/link/details/{soc_code}"

    summary_text, details_text = await asyncio.gather(
        _fetch_page_text(summary_url),
        _fetch_page_text(details_url),
    )

    sections = []
    if summary_text:
        sections.append(f"=== O*NET Summary for {soc_code} ===\n{summary_text[:5000]}")
    if details_text:
        sections.append(f"=== O*NET Detailed Work Activities for {soc_code} ===\n{details_text[:5000]}")

    research = "\n\n".join(sections) if sections else ""
    logger.info("O*NET research fetched: %d chars", len(research))

    return {"onet_research": research, "status": "researching_onet"}


async def risk_assessor_node(state: CareerPivotState) -> Dict[str, Any]:
    """Assess automation risk using real O*NET data as context."""
    from backend.shared.llm import build_llm, default_model, invoke_with_retry
    from langchain_core.messages import HumanMessage, SystemMessage

    role = state.get("parsed_role", "Unknown")
    soc_code = state.get("soc_code", "")
    skills = state.get("parsed_skills", [])
    industry = state.get("industry", "Unknown")
    onet_research = state.get("onet_research", "")

    llm = build_llm(model=default_model(), max_tokens=8192, temperature=0.0)

    onet_context = ""
    if onet_research:
        onet_context = (
            "\n\nIMPORTANT: Below is REAL data fetched from O*NET Online for this occupation. "
            "Use this actual data to ground your analysis — extract the real Work Activities, "
            "Knowledge, Skills, and Abilities listed on the page. Do NOT make up activities.\n\n"
            + onet_research[:6000]
        )

    system_prompt = (
        "You are an AI automation risk analyst. Use Frey & Osborne (2017) automation "
        "probability estimates and O*NET Work Activities.\n"
        + onet_context
        + "\n\nFor the given occupation:\n\n"
        "1. **Overall automation probability** — Frey & Osborne computerisation probability "
        "for this SOC code (0-100 scale).\n\n"
        "2. **Task breakdown** — use the REAL O*NET Work Activities from the data above. "
        "For each, estimate automation risk percentage.\n\n"
        "3. **Automation-resistant abilities** — O*NET abilities from this occupation that "
        "protect it from automation.\n\n"
        'Return ONLY valid JSON, no markdown:\n'
        '{\n'
        '  "automation_risk_score": 47.0,\n'
        '  "task_breakdown": [\n'
        '    {"task": "Analyzing Data or Information", "risk_pct": 78},\n'
        '    {"task": "Making Decisions and Solving Problems", "risk_pct": 25},\n'
        '    {"task": "Thinking Creatively", "risk_pct": 15}\n'
        '  ],\n'
        '  "resistant_abilities": ["Originality", "Social Perceptiveness"]\n'
        '}'
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"SOC Code: {soc_code}\nRole: {role}\nIndustry: {industry}\nSkills: {', '.join(skills[:15])}"),
    ]

    try:
        response = await invoke_with_retry(llm, messages)
        content = response.content
    except Exception as exc:
        logger.warning("risk_assessor LLM call failed: %s", str(exc)[:200])
        content = ""
    parsed = _safe_parse_json(
        content,
        {"automation_risk_score": 50.0, "task_breakdown": []},
    )

    return {
        "automation_risk_score": parsed.get("automation_risk_score", 50.0),
        "task_breakdown": parsed.get("task_breakdown", []),
        "resistant_abilities": parsed.get("resistant_abilities", []),
        "status": "assessing_risk",
    }


async def role_mapper_node(state: CareerPivotState) -> Dict[str, Any]:
    """Map adjacent roles using real O*NET data as context."""
    from backend.shared.llm import build_llm, default_model, invoke_with_retry
    from langchain_core.messages import HumanMessage, SystemMessage

    role = state.get("parsed_role", "Unknown")
    soc_code = state.get("soc_code", "")
    skills = state.get("parsed_skills", [])
    knowledge_areas = state.get("knowledge_areas", [])
    years = state.get("years_experience", 0)
    industry = state.get("industry", "Unknown")
    location = state.get("location", "Remote")
    onet_research = state.get("onet_research", "")

    llm = build_llm(model=default_model(), max_tokens=32768, temperature=0.0)

    onet_context = ""
    if onet_research:
        onet_context = (
            "\n\nREFERENCE DATA: Below is real O*NET data for the user's current occupation. "
            "Use this to understand their actual skill profile and find roles with genuine skill overlap.\n\n"
            + onet_research[:4000]
        )

    system_prompt = (
        "You are a career transition advisor with access to O*NET and BLS data.\n"
        + onet_context
        + "\n\nFind 4-5 pivot roles for this person. Ground your recommendations in real occupational data:\n\n"
        "**Required for each pivot role:**\n"
        "1. **O*NET SOC code** — real SOC code\n"
        "2. **Skill overlap** — percentage of user's O*NET KSA categories that overlap with target role\n"
        "3. **BLS salary data** — median annual wage, 25th and 90th percentiles\n"
        "4. **BLS projected job openings** — annual projected openings 2022-2032\n"
        "5. **BLS growth rate** — projected percent change 2022-2032\n"
        "6. **Entry education** — typical entry-level education\n"
        "7. **AI automation risk** — Frey & Osborne probability for the target SOC code\n"
        "8. **Missing skills** — specific O*NET skills/knowledge the user lacks\n"
        "9. **Skill comparison** — user KSA levels vs target requirements across 6-8 categories (0-100 scale)\n"
        "10. **Learning plan** — real certifications, courses, platforms\n\n"
        'Return ONLY valid JSON, no markdown:\n'
        '{\n'
        '  "recommended_pivots": [\n'
        '    {\n'
        '      "soc_code": "15-1211.01",\n'
        '      "role": "Health Informatics Specialist",\n'
        '      "skill_overlap_pct": 74.0,\n'
        '      "salary_range": {"min": 62000, "max": 132000, "median": 98000},\n'
        '      "market_demand": 18500,\n'
        '      "growth_rate": "16% much faster than average",\n'
        '      "entry_education": "Bachelor\'s degree",\n'
        '      "ai_risk_pct": 23.0,\n'
        '      "missing_skills": ["Health Information Systems", "HIPAA Compliance"],\n'
        '      "skill_comparison": {\n'
        '        "categories": ["Programming", "Data Analysis", "Communication", "Problem Solving", "Domain Knowledge", "Project Management"],\n'
        '        "user_scores": [85, 70, 75, 80, 30, 65],\n'
        '        "target_scores": [60, 90, 80, 85, 95, 70]\n'
        '      },\n'
        '      "learning_plan": [\n'
        '        {"week": "1-4", "topic": "Health Informatics Foundations", "resources": [{"name": "Coursera: Health Informatics (Johns Hopkins)", "hours": 40, "cost": "$49/mo"}]}\n'
        '      ],\n'
        '      "time_to_pivot_weeks": 12\n'
        '    }\n'
        '  ]\n'
        '}'
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Current SOC: {soc_code}\nCurrent role: {role}\nYears experience: {years}\nIndustry: {industry}\nKnowledge areas: {', '.join(knowledge_areas[:10])}\nSkills: {', '.join(skills[:15])}\nLocation: {location}"),
    ]

    try:
        response = await invoke_with_retry(llm, messages)
        content = response.content
    except Exception as exc:
        logger.warning("role_mapper LLM call failed: %s", str(exc)[:200])
        content = ""
    parsed = _safe_parse_json(
        content,
        {"recommended_pivots": []},
    )

    return {
        "recommended_pivots": parsed.get("recommended_pivots", []),
        "status": "mapping_roles",
    }


async def cross_industry_mapper_node(state: CareerPivotState) -> Dict[str, Any]:
    """Map transferable skills to creative cross-industry, cross-collar roles."""
    from backend.shared.llm import build_llm, premium_model, invoke_with_retry
    from langchain_core.messages import HumanMessage, SystemMessage

    role = state.get("parsed_role", "Unknown")
    soc_code = state.get("soc_code", "")
    skills = state.get("parsed_skills", [])
    knowledge_areas = state.get("knowledge_areas", [])
    abilities = state.get("abilities", [])
    resistant_abilities = state.get("resistant_abilities", [])
    years = state.get("years_experience", 0)
    industry = state.get("industry", "Unknown")
    onet_research = state.get("onet_research", "")

    llm = build_llm(model=premium_model(), max_tokens=32768, temperature=0.7)

    onet_context = ""
    if onet_research:
        onet_context = (
            "\n\nREFERENCE DATA from O*NET for the user's current occupation:\n"
            + onet_research[:4000]
        )

    system_prompt = (
        "You are a creative career strategist who finds UNEXPECTED career paths by mapping "
        "transferable skills across industries and collar types (white/blue/pink collar).\n"
        + onet_context
        + "\n\n## YOUR TASK\n"
        "Identify 4-6 of the user's strongest transferable skills and map each to 2-4 "
        "diverse target roles in DIFFERENT industries.\n\n"
        "## MANDATORY RULES\n"
        "1. **CROSS-COLLAR DIVERSITY**: If the user is white-collar, at least 30% of target "
        "roles MUST be blue-collar or pink-collar (and vice versa). A carpenter should see "
        "UX Researcher. A software engineer should see Wind Turbine Technician.\n"
        "2. **NO ADJACENT ROLES**: Do NOT suggest roles in the same industry or obvious lateral "
        "moves. 'Software Developer → Data Scientist' is too obvious. Think bigger.\n"
        "3. **CREATIVE TRANSFERS**: Find unexpected contexts where skills genuinely apply. "
        "Spatial reasoning → UX design. Project management → Film production. Debugging → "
        "Medical diagnostics. Problem decomposition → Culinary arts.\n"
        "4. **AI-RESISTANT BIAS**: Prefer roles that are hard to automate. Flag each role.\n"
        "5. **REAL DATA**: Use BLS salary ranges and demand levels. Don't invent numbers.\n"
        "6. **EXPLAIN WHY**: Each bridge must have a 2-3 sentence 'why' explaining the "
        "skill transfer in plain language a non-expert would understand.\n\n"
        "## OUTPUT FORMAT\n"
        "Return ONLY valid JSON, no markdown:\n"
        "{\n"
        '  "skill_bridges": [\n'
        "    {\n"
        '      "your_skill": "Spatial Reasoning",\n'
        '      "skill_category": "Cognitive",\n'
        '      "transfers_to": [\n'
        "        {\n"
        '          "industry": "Design",\n'
        '          "role": "UX Researcher",\n'
        '          "why": "Your ability to mentally rotate and manipulate objects translates directly to understanding how users navigate digital spaces. UX research relies on spatial thinking to design intuitive interfaces.",\n'
        '          "salary_range": {"min": 65000, "max": 130000, "median": 95000},\n'
        '          "demand": "High",\n'
        '          "growth_rate": "16% much faster than average",\n'
        '          "collar": "white",\n'
        '          "ai_resistant": true\n'
        "        }\n"
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Skill categories: Technical, Interpersonal, Cognitive, Physical\n"
        "Collar types: white, blue, pink\n"
        "Demand levels: High, Medium, Low"
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=(
            f"Current SOC: {soc_code}\n"
            f"Current role: {role}\n"
            f"Industry: {industry}\n"
            f"Years experience: {years}\n"
            f"Skills: {', '.join(skills[:15])}\n"
            f"Knowledge areas: {', '.join(knowledge_areas[:10])}\n"
            f"Abilities: {', '.join(abilities[:10])}\n"
            f"AI-resistant abilities: {', '.join(resistant_abilities[:8])}"
        )),
    ]

    logger.info("cross_industry_mapper: calling LLM for %s (%s)", role, soc_code)
    try:
        response = await invoke_with_retry(llm, messages)
        content = response.content
        logger.info("cross_industry_mapper: got %d chars response", len(content) if content else 0)
    except Exception as exc:
        logger.warning("cross_industry_mapper LLM call failed: %s", str(exc)[:200])
        content = ""
    parsed = _safe_parse_json(
        content,
        {"skill_bridges": []},
    )

    bridges = parsed.get("skill_bridges", [])
    logger.info("cross_industry_mapper: parsed %d skill bridges", len(bridges))
    return {
        "skill_bridges": bridges,
        "status": "mapping_cross_industry",
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
    g.add_node("onet_researcher", onet_researcher_node)
    g.add_node("risk_assessor", risk_assessor_node)
    g.add_node("role_mapper", role_mapper_node)
    g.add_node("cross_industry_mapper", cross_industry_mapper_node)
    g.add_node("report_generator", report_generator_node)

    g.add_edge(START, "skill_parser")
    g.add_edge("skill_parser", "onet_researcher")
    g.add_edge("onet_researcher", "risk_assessor")
    g.add_edge("risk_assessor", "role_mapper")
    g.add_edge("role_mapper", "cross_industry_mapper")
    g.add_edge("cross_industry_mapper", "report_generator")
    g.add_edge("report_generator", END)

    return g.compile(checkpointer=checkpointer)
