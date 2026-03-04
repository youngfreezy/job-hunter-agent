"""Discovery Agent -- searches job boards for listings matching the user's SearchConfig.

Phase 1: Simulated discovery using Claude Sonnet to generate realistic mock listings.
Phase 2: Replace with real Playwright-based scraping across multiple boards.
"""

from __future__ import annotations

import json
import logging
import random
from typing import Any, Dict, List
from uuid import uuid4

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Send

from backend.shared.config import settings
from backend.shared.models.schemas import (
    ATSType,
    JobBoard,
    JobListing,
    SearchConfig,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "claude-sonnet-4-6"
DISCOVERY_MIN_RESULTS = 20
DISCOVERY_MAX_RESULTS = 50

BOARDS = list(JobBoard)
ATS_TYPES = list(ATSType)

SYSTEM_PROMPT = """\
You are a realistic job-listing generator used for development and testing.
Given a search configuration, produce a JSON array of realistic job listings.

Each listing object MUST have these fields:
- title (str): realistic job title matching the keywords
- company (str): realistic company name (mix of well-known and lesser-known companies)
- location (str): city/state or "Remote" matching the search locations
- url (str): a plausible job-board URL (e.g. https://www.indeed.com/viewjob?jk=abc123)
- salary_range (str | null): e.g. "$120,000 - $160,000/year" or null
- description_snippet (str): 2-3 sentence description of the role
- posted_date (str): a realistic recent date in YYYY-MM-DD format within the last 30 days
- is_remote (bool): whether the role is remote
- is_easy_apply (bool): randomly true ~30% of the time

Rules:
- Make titles, companies, and descriptions diverse and realistic.
- Salary ranges should be plausible for the role level.
- Vary seniority, company size, and tech stacks in the descriptions.
- Return ONLY valid JSON -- an array of objects. No markdown, no explanation.
"""


# ---------------------------------------------------------------------------
# Fan-out helper
# ---------------------------------------------------------------------------

def dispatch_discovery(state: Dict[str, Any]) -> List[Send]:
    """Return Send objects for parallel board scraping.

    Phase 1: Returns a single Send since we use simulated discovery.
    Phase 2: Will fan out one Send per board in state["search_config"].
    """
    return [Send("discovery", state)]


# ---------------------------------------------------------------------------
# Main agent
# ---------------------------------------------------------------------------

async def run_discovery_agent(state: Dict[str, Any]) -> dict:
    """Discover job listings matching the user's search configuration.

    In Phase 1 this calls Claude Sonnet to generate realistic mock listings.
    Returns a dict that merges into JobHunterState.
    """
    try:
        search_config: SearchConfig | None = state.get("search_config")

        # Fallback: build a minimal SearchConfig from raw state fields
        if search_config is None:
            search_config = SearchConfig(
                keywords=state.get("keywords", []),
                locations=state.get("locations", ["Remote"]),
                remote_only=state.get("remote_only", False),
                salary_min=state.get("salary_min"),
            )

        num_listings = random.randint(
            DISCOVERY_MIN_RESULTS,
            DISCOVERY_MAX_RESULTS,
        )

        logger.info(
            "Discovery agent starting -- keywords=%s, locations=%s, target=%d",
            search_config.keywords,
            search_config.locations,
            num_listings,
        )

        # ----- Call Claude Sonnet for realistic mock data -----
        llm = ChatAnthropic(
            model=DEFAULT_MODEL,
            api_key=settings.ANTHROPIC_API_KEY,
            max_tokens=4096,
            temperature=1.0,  # more variety in listings
        )

        user_prompt = (
            f"Generate exactly {num_listings} job listings for this search:\n"
            f"- Keywords: {', '.join(search_config.keywords)}\n"
            f"- Locations: {', '.join(search_config.locations)}\n"
            f"- Remote only: {search_config.remote_only}\n"
            f"- Salary minimum: {search_config.salary_min or 'not specified'}\n"
            f"- Experience level: {search_config.experience_level or 'not specified'}\n"
            f"- Job type: {search_config.job_type or 'full-time'}\n"
        )

        response = await llm.ainvoke(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ]
        )

        raw_text = response.content
        if isinstance(raw_text, list):
            # Some models return a list of content blocks
            raw_text = "".join(
                block if isinstance(block, str) else block.get("text", "")
                for block in raw_text
            )

        raw_listings: List[dict] = json.loads(raw_text)

        # ----- Convert raw dicts into JobListing models -----
        discovered: List[JobListing] = []
        for item in raw_listings:
            listing = JobListing(
                id=str(uuid4()),
                title=item["title"],
                company=item["company"],
                location=item["location"],
                url=item.get("url", f"https://www.indeed.com/viewjob?jk={uuid4().hex[:12]}"),
                board=random.choice(BOARDS),
                ats_type=random.choice(ATS_TYPES),
                salary_range=item.get("salary_range"),
                description_snippet=item.get("description_snippet"),
                posted_date=item.get("posted_date"),
                is_remote=item.get("is_remote", False),
                is_easy_apply=item.get("is_easy_apply", False),
            )
            discovered.append(listing)

        logger.info("Discovery agent finished -- %d listings generated", len(discovered))

        return {
            "discovered_jobs": discovered,
            "agent_statuses": {"discovery": "done"},
            "status": "scoring",
        }

    except Exception as e:
        logger.exception("Discovery agent failed")
        return {
            "errors": [f"discovery failed: {str(e)}"],
            "agent_statuses": {"discovery": "failed"},
        }
