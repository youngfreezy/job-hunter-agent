# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Intake Agent -- parses user inputs + resume into a structured SearchConfig."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import Field

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
1. Preserve explicitly supplied keyword phrases, locations, remote-only choice,
   and minimum salary. Do not split, paraphrase, broaden, or replace those fields.
2. Only when keywords are absent, infer at most 6 relevant job-title phrases.
   Do not exhaustively list every skill from the resume.
3. If resume text is provided, extract:
   - Relevant job-title keywords only when no keywords were supplied.
   - An experience level estimate: "entry", "mid", "senior", or "executive".
   - Inferred job type if not specified (e.g. "full-time").
3. Respect explicit user preferences -- they always take priority over
   inferences from the resume.
4. Additional discovery prose supplies preferences and missing fields; it must
   not replace the explicitly supplied structured fields.
5. Populate exclude_title_keywords and exclude_companies from explicit exclusions.
6. A target or desired salary is not a minimum. Only populate salary_min from
   an explicit minimum, including the owner's saved application rules.
"""

PROMPT_INTAKE_SYSTEM_PROMPT = """\
Extract a search configuration from the user's primary discovery prompt.
The prompt alone determines the requested roles. Its explicit locations and
work arrangements take priority; otherwise use the separate preference fields.
Do not add roles, technologies, specializations, or seniority terms from the resume.
Use the resume only to estimate experience_level; it does not expand roles.

Return primary_role as the broad core job-title phrase that faithfully matches
the request, without unnecessary modifiers (for an AI software engineering
request, for example, AI Engineer). Return at most two additional faithful
job-title variants in keywords. Do not add unrelated roles to reach the limit.
Do not broaden past an explicit specialization or other restriction.

Preserve the owner's saved eligibility rules and explicit preferences,
including exclusions and minimum compensation. A desired salary is not a
minimum; only populate salary_min from an explicit minimum. For hybrid or
remote, use work_arrangements=['hybrid', 'remote'], remote_only=false, and
retain the requested city. For remote-only, use work_arrangements=['remote']
and remote_only=true. Extract explicit title/company exclusions.
"""


class _PromptSearchConfig(SearchConfig):
    primary_role: str = Field(min_length=1, description="Broad core role explicitly requested by the discovery prompt.")
    keywords: list[str] = Field(default_factory=list, max_length=2, description="At most two additional role phrases from the prompt; never resume-derived roles.")


def _normalize_prompt_search(config: _PromptSearchConfig) -> SearchConfig:
    """Make the core phrase first and bound the actual query count in code."""
    primary = ' '.join(config.primary_role.split())
    if not primary:
        raise ValueError('Discovery prompt did not produce a primary role.')
    phrases: dict[str, str] = {}
    for value in [primary, *config.keywords]:
        phrase = ' '.join(value.split())
        if phrase:
            phrases.setdefault(phrase.casefold(), phrase)
    return SearchConfig.model_validate({
        **config.model_dump(exclude={'primary_role'}),
        'keywords': list(phrases.values())[:3],
    })


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
        preferences = state.get("preferences") or {}
        raw_prompt = preferences.get("discovery_prompt")
        discovery_prompt = raw_prompt.strip() if isinstance(raw_prompt, str) else ""
        keywords = state.get("keywords", [])
        # QuickStart can carry resume-derived chips beside its primary prompt.
        # Custom Search marks fields as intentional, even when a prompt is also
        # present. Unmarked keyword-only API/Autopilot searches are structured.
        structured_search = not discovery_prompt or preferences.get("search_input_mode") == "structured"
        prompt_driven = bool(discovery_prompt) and not (structured_search and keywords)
        llm = build_llm(model=default_model(), max_tokens=4096, temperature=0.0)
        structured_llm = llm.with_structured_output(_PromptSearchConfig if prompt_driven else SearchConfig)

        # -- Build the user message from available state fields -------------
        parts: list[str] = []

        if discovery_prompt:
            label = "Primary discovery prompt" if prompt_driven else "Additional discovery preferences (explicit form fields take precedence)"
            parts.append(f"{label}:\n{discovery_prompt}")
        if keywords and not prompt_driven:
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

        additional_preferences = dict(preferences)
        if discovery_prompt:
            additional_preferences.pop('discovery_prompt', None)
        if additional_preferences:
            parts.append(f"Additional preferences: {json.dumps(additional_preferences)}")
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
            SystemMessage(content=PROMPT_INTAKE_SYSTEM_PROMPT if prompt_driven else INTAKE_SYSTEM_PROMPT),
            HumanMessage(content=user_message),
        ]

        search_config: SearchConfig = await invoke_with_retry(structured_llm, messages)
        if prompt_driven:
            search_config = _normalize_prompt_search(search_config)

        if structured_search:
            # Enforce the input contract in code; a prompt alone cannot prevent
            # model expansions from changing a user's targeted query.
            if keywords:
                search_config.keywords = list(dict.fromkeys(k.strip() for k in keywords if k.strip()))
            if "locations" in state:
                search_config.locations = list(state["locations"])
            if "remote_only" in state:
                search_config.remote_only = state["remote_only"]
                search_config.work_arrangements = ["remote"] if state["remote_only"] else []
            if salary_min is not None:
                search_config.salary_min = salary_min

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
