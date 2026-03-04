"""Intake Agent -- parses user inputs + resume into a structured SearchConfig."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from backend.orchestrator.pipeline.state import JobHunterState
from backend.shared.config import get_settings
from backend.shared.models.schemas import SearchConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
INTAKE_SYSTEM_PROMPT = """\
You are the Intake Agent for a job-hunting platform.

Your job is to take raw user inputs (keywords, locations, preferences) along
with optional resume text and produce a single, precise JSON object that
downstream agents will use to discover job listings.

**Instructions**
1. Normalise and deduplicate keywords.  Expand obvious abbreviations
   (e.g. "ML" -> "Machine Learning", "SWE" -> "Software Engineer").
2. If resume text is provided, extract:
   - Additional relevant keywords the user may not have listed.
   - An experience level estimate: "entry", "mid", "senior", or "executive".
   - Inferred job type if not specified (e.g. "full-time").
3. Respect explicit user preferences -- they always take priority over
   inferences from the resume.
4. Return **only** valid JSON matching the schema below.  No markdown fences,
   no commentary.

**Output JSON schema**
{
  "keywords": ["string"],
  "locations": ["string"],
  "remote_only": bool,
  "salary_min": int | null,
  "experience_level": "entry" | "mid" | "senior" | "executive" | null,
  "job_type": "full-time" | "contract" | "part-time" | null,
  "company_size": "startup" | "mid" | "enterprise" | null,
  "exclude_companies": ["string"]
}
"""


# ---------------------------------------------------------------------------
# Agent entry-point
# ---------------------------------------------------------------------------
async def run_intake_agent(state: JobHunterState) -> Dict[str, Any]:
    """Parse user keywords, resume text, and preferences into a SearchConfig.

    Returns a dict that LangGraph merges back into the pipeline state.
    """
    try:
        settings = get_settings()

        llm = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.ANTHROPIC_API_KEY,
            temperature=0,
            model_kwargs={"response_format": {"type": "json_object"}},
        )

        # -- Build the user message from available state fields -------------
        parts: list[str] = []

        keywords = state.get("keywords", [])
        if keywords:
            parts.append(f"Keywords: {', '.join(keywords)}")

        locations = state.get("locations", [])
        if locations:
            parts.append(f"Locations: {', '.join(locations)}")

        if state.get("remote_only"):
            parts.append("Remote only: yes")

        salary_min = state.get("salary_min")
        if salary_min is not None:
            parts.append(f"Minimum salary: ${salary_min:,}")

        preferences = state.get("preferences", {})
        if preferences:
            parts.append(f"Additional preferences: {json.dumps(preferences)}")

        resume_text = state.get("resume_text", "")
        if resume_text:
            parts.append(
                f"--- BEGIN RESUME ---\n{resume_text}\n--- END RESUME ---"
            )

        user_message = "\n\n".join(parts) if parts else "No inputs provided."

        # -- Invoke the LLM ------------------------------------------------
        messages = [
            SystemMessage(content=INTAKE_SYSTEM_PROMPT),
            HumanMessage(content=user_message),
        ]

        response = await llm.ainvoke(messages)
        raw_json = response.content

        # Parse and validate through the Pydantic model
        parsed = json.loads(raw_json)
        search_config = SearchConfig(**parsed)

        logger.info(
            "Intake agent produced SearchConfig with %d keywords for %s",
            len(search_config.keywords),
            search_config.locations,
        )

        return {
            "search_config": search_config,
            "status": "coaching",
            "agent_statuses": {"intake": "done"},
        }

    except Exception as e:
        logger.exception("Intake agent failed")
        return {
            "errors": [f"Intake agent failed: {str(e)}"],
            "agent_statuses": {"intake": "failed"},
        }
