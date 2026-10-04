# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Intake Agent -- parses user inputs + resume into a structured SearchConfig."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage

from backend.orchestrator.pipeline.state import JobHunterState
from backend.shared.llm import build_llm, default_model, invoke_with_retry
from backend.shared.models.schemas import SearchConfig
from backend.shared.config import get_settings

# SearchConfig is already a Pydantic model -- use it directly with structured output

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
INTAKE_SYSTEM_PROMPT = """\
You are the Intake Agent for a job-hunting platform.

Your job is to take raw user inputs (keywords, locations, preferences) along
with optional resume text and produce a structured search configuration that
downstream agents will use to discover job listings.

**Instructions**
1. Normalise and deduplicate keywords.  Expand obvious abbreviations
   (e.g. "ML" -> "Machine Learning", "SWE" -> "Software Engineer").
2. Keep the final keyword list to **at most 6 keywords**. Focus on the
   user's original keywords plus 1-2 high-value expansions from the resume.
   Do NOT exhaustively list every skill from the resume.
3. If resume text is provided, extract:
   - 1-2 additional relevant job-title keywords the user may not have listed.
   - An experience level estimate: "entry", "mid", "senior", or "executive".
   - Inferred job type if not specified (e.g. "full-time").
3. Respect explicit user preferences -- they always take priority over
   inferences from the resume.
4. The discovery_prompt is the user's primary search instruction. Extract
   roles and locations from it. Never replace its roles with resume-derived
   roles. For 'hybrid or remote', set work_arrangements to ['hybrid', 'remote']
   and remote_only=false. Keep the specified city for hybrid work. For
   remote-only requests set remote_only=true and work_arrangements=['remote'].
5. For discovery_prompt searches, keywords must be complete job-title search
   phrases (e.g. 'Applied AI Engineer', 'AI Software Engineer'), not isolated
   skills like 'AI', 'LLM', or 'AI-Native'. Use at most three focused phrases.
   Populate exclude_title_keywords and exclude_companies from explicit exclusions.
6. A target or desired salary is not a minimum. Only populate salary_min from
   an explicit minimum, including the owner's saved application rules.
"""


# ---------------------------------------------------------------------------
# Agent entry-point
# ---------------------------------------------------------------------------
async def run_intake_agent(state: JobHunterState) -> Dict[str, Any]:
    """Parse user keywords, resume text, and preferences into a SearchConfig.

    Returns a dict that LangGraph merges back into the pipeline state.
    """
    # Quick Apply: if job_urls are provided, hydrate them into JobListings
    # and skip the LLM-based keyword extraction (keywords may be empty)
    job_urls = state.get("job_urls", [])
    if job_urls:
        from backend.orchestrator.agents.url_hydrator import hydrate_urls
        try:
            if get_settings().INDEED_ONLY:
                from backend.browser.tools.indeed_hydration import hydrate_indeed_urls
                hydrated = await hydrate_indeed_urls(
                    job_urls, user_id=state.get("user_id", ""),
                    session_id=state.get("session_id", ""),
                )
            else:
                hydrated = await hydrate_urls(job_urls)
            logger.info("Quick Apply: hydrated %d URLs into JobListings", len(hydrated))
            return {
                "search_config": SearchConfig(
                    keywords=state.get("keywords") or ["Quick Apply"],
                    locations=state.get("locations", ["Remote"]),
                    remote_only=state.get("remote_only", False),
                ),
                "discovered_jobs": hydrated,
                "status": "coaching",
                "agent_statuses": {"intake": "done"},
            }
        except Exception as exc:
            logger.exception("URL hydration failed: %s", exc)
            return {
                "errors": [f"URL hydration failed: {exc}"],
                "agent_statuses": {"intake": "failed"},
            }

    try:
        llm = build_llm(model=default_model(), max_tokens=4096, temperature=0.0)
        structured_llm = llm.with_structured_output(SearchConfig)

        # -- Build the user message from available state fields -------------
        parts: list[str] = []

        keywords = state.get("keywords", [])
        if keywords:
            parts.append(f"Keywords: {', '.join(keywords)}")

        remote_only = state.get("remote_only", False)

        if remote_only:
            parts.append("Remote only: yes — ignore any physical locations")
        else:
            locations = state.get("locations", [])
            if locations:
                parts.append(f"Locations: {', '.join(locations)}")

        salary_min = state.get("salary_min")
        if salary_min is not None:
            parts.append(f"Minimum salary: ${salary_min:,}")

        preferences = state.get("preferences", {})
        if preferences:
            parts.append(f"Additional preferences: {json.dumps(preferences)}")
        from backend.shared.application_rules import load_application_rules, allows_unpublished_salary
        owner_rules = load_application_rules(state.get("user_id"))
        if owner_rules:
            parts.append(f"Owner's saved application rules:\n{owner_rules}")

        resume_text = state.get("resume_text", "")
        if resume_text:
            parts.append(
                f"--- BEGIN RESUME ---\n{resume_text}\n--- END RESUME ---"
            )

        user_message = "\n\n".join(parts) if parts else "No inputs provided."

        # -- Invoke the LLM with structured output -------------------------
        messages = [
            SystemMessage(content=INTAKE_SYSTEM_PROMPT),
            HumanMessage(content=user_message),
        ]

        search_config: SearchConfig = await invoke_with_retry(structured_llm, messages)

        # Only saved owner permission may widen salary discovery. Keep the
        # minimum intact for published-pay/offer screening downstream.
        search_config.allow_unpublished_salary = allows_unpublished_salary(owner_rules)

        # Override search_radius with user's explicit preference (LLM doesn't decide this)
        user_radius = state.get("search_radius", 100)
        search_config.search_radius = user_radius

        logger.info(
            "Intake agent produced SearchConfig with %d keywords for %s",
            len(search_config.keywords),
            search_config.locations,
        )

        return {
            "search_config": search_config,
            "keywords": search_config.keywords,
            "locations": search_config.locations,
            "remote_only": search_config.remote_only,
            "status": "coaching",
            "agent_statuses": {"intake": "done"},
        }

    except Exception as e:
        logger.exception("Intake agent failed")
        return {
            "errors": [f"Intake agent failed: {str(e)}"],
            "agent_statuses": {"intake": "failed"},
        }


# Alias for graph.py compatibility
run = run_intake_agent
