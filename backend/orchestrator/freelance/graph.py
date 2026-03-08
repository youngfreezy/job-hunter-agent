# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""LangGraph graph definition for the Freelance/Contract Matchmaker."""

from __future__ import annotations

import logging
from typing import Any, Dict

from langgraph.graph import END, START, StateGraph

from backend.orchestrator.freelance.state import FreelanceState

logger = logging.getLogger(__name__)


async def profile_generator_node(state: FreelanceState) -> Dict[str, Any]:
    """Generate platform-specific freelance profiles from resume."""
    from backend.shared.llm import build_llm, default_model, invoke_with_retry
    from langchain_core.messages import HumanMessage, SystemMessage

    resume = state.get("resume_text", "")
    platforms = state.get("platforms", ["upwork"])
    rate_min = state.get("hourly_rate_min", 50)
    rate_max = state.get("hourly_rate_max", 120)

    llm = build_llm(model=default_model(), max_tokens=4096, temperature=0.3)

    messages = [
        SystemMessage(content=f"""You are a freelance profile optimization expert.
Create platform-specific profiles for each platform: {', '.join(platforms)}.

Each profile should:
1. Have a compelling headline (platform-specific format)
2. Bio that highlights relevant experience for freelance work
3. Optimal skills tags for the platform
4. Portfolio suggestions based on past experience

Return as JSON:
{{
  "profiles": [
    {{
      "platform": "upwork",
      "bio": "...",
      "headline": "...",
      "hourly_rate": {(rate_min + rate_max) / 2},
      "skills_tags": ["React", "Node.js", ...],
      "portfolio_suggestions": ["Project X - describe as...", ...]
    }}
  ]
}}"""),
        HumanMessage(content=f"Resume:\n{resume[:2000]}"),
    ]

    response = await invoke_with_retry(llm, messages)
    import json
    try:
        parsed = json.loads(response.content)
        profiles = parsed.get("profiles", [])
    except (json.JSONDecodeError, AttributeError):
        profiles = []

    return {
        "profiles": profiles,
        "status": "generating_profiles",
    }


async def gig_discovery_node(state: FreelanceState) -> Dict[str, Any]:
    """Discover matching gigs across platforms (simulated for MVP)."""
    from backend.shared.llm import build_llm, default_model, invoke_with_retry
    from langchain_core.messages import HumanMessage, SystemMessage

    platforms = state.get("platforms", ["upwork"])
    project_types = state.get("project_types", [])
    rate_min = state.get("hourly_rate_min", 50)
    rate_max = state.get("hourly_rate_max", 120)
    profiles = state.get("profiles", [])
    skills = []
    for p in profiles:
        skills.extend(p.get("skills_tags", []))
    skills = list(set(skills))

    llm = build_llm(model=default_model(), max_tokens=4096, temperature=0.5)

    messages = [
        SystemMessage(content="""You are simulating a multi-platform gig search for development purposes.
Generate 8-12 realistic freelance gig listings that would match a freelancer with the given skills.

For each gig, return:
{
  "discovered_gigs": [
    {
      "id": "gig_001",
      "title": "React Dashboard for Fintech Startup",
      "platform": "upwork",
      "url": "https://upwork.com/jobs/~example",
      "client_name": "TechFin Inc",
      "budget_type": "fixed",
      "budget_min": 3000,
      "budget_max": 5000,
      "duration": "2-3 weeks",
      "description_snippet": "Looking for experienced React developer...",
      "posted_date": "1 hour ago",
      "proposals_count": 3,
      "match_score": 92.0
    }
  ]
}

Make gigs realistic and varied across platforms. Include mix of fixed and hourly. Vary match scores 60-95%."""),
        HumanMessage(content=f"Skills: {', '.join(skills)}\nPlatforms: {', '.join(platforms)}\nProject types: {', '.join(project_types)}\nRate range: ${rate_min}-${rate_max}/hr"),
    ]

    response = await invoke_with_retry(llm, messages)
    import json
    try:
        parsed = json.loads(response.content)
        gigs = parsed.get("discovered_gigs", [])
    except (json.JSONDecodeError, AttributeError):
        gigs = []

    return {
        "discovered_gigs": gigs,
        "scored_gigs": sorted(gigs, key=lambda g: g.get("match_score", 0), reverse=True),
        "status": "discovering_gigs",
    }


async def proposal_generator_node(state: FreelanceState) -> Dict[str, Any]:
    """Generate proposals for top-matching gigs."""
    from backend.shared.llm import build_llm, default_model, invoke_with_retry
    from langchain_core.messages import HumanMessage, SystemMessage

    gigs = state.get("scored_gigs", [])[:5]  # Top 5 gigs
    resume = state.get("resume_text", "")
    profiles = state.get("profiles", [])

    if not gigs:
        return {"proposals": {}, "status": "generating_proposals"}

    llm = build_llm(model=default_model(), max_tokens=4096, temperature=0.4)
    proposals = {}

    for gig in gigs:
        messages = [
            SystemMessage(content="""You are an expert freelance proposal writer.
Write a personalized proposal for this gig that:
1. Opens with a hook referencing the client's specific need
2. Shows relevant experience from the freelancer's background
3. Proposes a clear approach/timeline
4. Ends with a confident close

Keep it 150-250 words. Match the client's language and tone.
Return just the proposal text, no JSON."""),
            HumanMessage(content=f"Gig: {gig.get('title', '')}\nDescription: {gig.get('description_snippet', '')}\nClient: {gig.get('client_name', '')}\nBudget: {gig.get('budget_type', '')} ${gig.get('budget_min', '')}-${gig.get('budget_max', '')}\n\nFreelancer Resume:\n{resume[:1000]}"),
        ]

        response = await invoke_with_retry(llm, messages)
        proposals[gig.get("id", "")] = response.content

    return {
        "proposals": proposals,
        "status": "generating_proposals",
    }


def build_freelance_graph(checkpointer=None):
    """Build the Freelance Matchmaker StateGraph."""
    g = StateGraph(FreelanceState)

    g.add_node("profile_generator", profile_generator_node)
    g.add_node("gig_discovery", gig_discovery_node)
    g.add_node("proposal_generator", proposal_generator_node)

    g.add_edge(START, "profile_generator")
    g.add_edge("profile_generator", "gig_discovery")
    g.add_edge("gig_discovery", "proposal_generator")
    g.add_edge("proposal_generator", END)

    return g.compile(checkpointer=checkpointer)
