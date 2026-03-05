"""Career Coach Agent -- the emotional and strategic heart of JobHunter.

Analyses the user's resume, rewrites it like a salesperson pitching their best
client, coaches away impostor-syndrome language, drafts a master cover letter
template, offers LinkedIn advice, and scores the resume on five dimensions.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from backend.orchestrator.pipeline.state import JobHunterState
from backend.shared.config import get_settings
from backend.shared.models.schemas import CoachOutput, ResumeScore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
COACH_SYSTEM_PROMPT = """\
You are the Career Coach Agent -- the user's biggest advocate and professional
hype-person.  Your tone is warm, encouraging, and confident.  You believe in
this person's potential even when they don't, and you communicate like a
world-class sales executive pitching their star candidate to a Fortune 500
hiring committee.

You will receive the user's resume text, optional LinkedIn URL, job-search
keywords, and a structured SearchConfig.  Your job is to produce a single JSON
object containing ALL of the following:

### 1. Resume Analysis & Rewrite (`rewritten_resume`)
- Identify undersold skills, weak or passive action verbs, and missing
  industry keywords.
- Rewrite the resume as a persuasive, achievement-driven narrative.
  Quantify wherever possible ("managed a team" -> "led a cross-functional
  team of 8 engineers, delivering the project 2 weeks ahead of schedule").
- Preserve factual accuracy -- never fabricate experience.

### 2. Impostor Syndrome Coaching (`confidence_message`)
- Scan the original resume for hedging language ("assisted with", "helped",
  "was responsible for", "exposure to") and note what you replaced.
- Provide a short, powerful encouragement message (3-5 sentences) that
  reframes the user's experience as genuinely impressive.  Be specific about
  *what* makes them strong.

### 3. LinkedIn Profile Advice (`linkedin_advice`)
- If a LinkedIn URL was provided, generate a list of 5-8 actionable tips to
  improve their profile (headline, summary, featured section, skills
  endorsements, activity strategy).
- If no URL was provided, return general best-practice tips.

### 4. Master Cover Letter Template (`cover_letter_template`)
- Generate a professional cover letter that uses placeholders:
  [COMPANY], [ROLE], [SPECIFIC_REASON].
- The letter should sound human, enthusiastic, and specific enough to feel
  personal once the placeholders are filled in.
- 3-4 paragraphs maximum.

### 5. Resume Score (`resume_score`)
Score the ORIGINAL resume (before your rewrite) on a 0-100 scale with this
breakdown:
- `overall`: weighted average
- `keyword_density`: how well it matches the target keywords
- `impact_metrics`: use of numbers, outcomes, and measurable achievements
- `ats_compatibility`: clean formatting, standard section headings, no tables/graphics
- `readability`: clear language, appropriate length, logical flow
- `formatting`: consistent styling, bullet usage, white space
- `feedback`: list of 3-5 specific improvement suggestions

### 6. Strengths & Improvement Areas
- `key_strengths`: 3-5 specific strengths you identified
- `improvement_areas`: 3-5 concrete areas to develop

**Output JSON schema** (return ONLY valid JSON, no markdown fences):
{
  "rewritten_resume": "string",
  "resume_score": {
    "overall": int,
    "keyword_density": int,
    "impact_metrics": int,
    "ats_compatibility": int,
    "readability": int,
    "formatting": int,
    "feedback": ["string"]
  },
  "cover_letter_template": "string",
  "linkedin_advice": ["string"],
  "confidence_message": "string",
  "key_strengths": ["string"],
  "improvement_areas": ["string"]
}
"""


# ---------------------------------------------------------------------------
# Agent entry-point
# ---------------------------------------------------------------------------
async def run_career_coach_agent(state: JobHunterState) -> Dict[str, Any]:
    """Analyse resume, rewrite it, coach the user, and score the original.

    Returns a dict that LangGraph merges back into the pipeline state.
    """
    try:
        settings = get_settings()

        llm = ChatAnthropic(
            model="claude-opus-4-6",
            api_key=settings.ANTHROPIC_API_KEY,
            temperature=0,
            max_tokens=4096,
        )

        # -- Build user message from state ----------------------------------
        parts: list[str] = []

        resume_text = state.get("resume_text", "")
        if resume_text:
            parts.append(
                f"--- BEGIN RESUME ---\n{resume_text}\n--- END RESUME ---"
            )
        else:
            parts.append("(No resume text provided -- generate advice based on keywords only.)")

        linkedin_url = state.get("linkedin_url")
        if linkedin_url:
            parts.append(f"LinkedIn profile URL: {linkedin_url}")
        else:
            parts.append("LinkedIn URL: not provided")

        keywords = state.get("keywords", [])
        if keywords:
            parts.append(f"Target job keywords: {', '.join(keywords)}")

        search_config = state.get("search_config")
        if search_config is not None:
            # SearchConfig is a Pydantic model -- serialise for the prompt
            config_dict = (
                search_config.model_dump()
                if hasattr(search_config, "model_dump")
                else search_config.dict()
            )
            parts.append(
                f"Structured SearchConfig:\n{json.dumps(config_dict, indent=2)}"
            )

        user_message = "\n\n".join(parts)

        # -- Invoke the LLM ------------------------------------------------
        messages = [
            SystemMessage(content=COACH_SYSTEM_PROMPT),
            HumanMessage(content=user_message),
        ]

        response = await llm.ainvoke(messages)
        raw_json = response.content

        # -- Parse and validate through Pydantic ----------------------------
        parsed = json.loads(raw_json)

        resume_score = ResumeScore(**parsed["resume_score"])

        coach_output = CoachOutput(
            rewritten_resume=parsed["rewritten_resume"],
            resume_score=resume_score,
            cover_letter_template=parsed["cover_letter_template"],
            linkedin_advice=parsed.get("linkedin_advice", []),
            confidence_message=parsed["confidence_message"],
            key_strengths=parsed.get("key_strengths", []),
            improvement_areas=parsed.get("improvement_areas", []),
        )

        logger.info(
            "Career Coach scored resume at %d/100 (keyword_density=%d, "
            "impact_metrics=%d, ats_compatibility=%d)",
            resume_score.overall,
            resume_score.keyword_density,
            resume_score.impact_metrics,
            resume_score.ats_compatibility,
        )

        return {
            "coach_output": coach_output,
            "coached_resume": coach_output.rewritten_resume,
            "cover_letter_template": coach_output.cover_letter_template,
            "status": "discovering",
            "agent_statuses": {"career_coach": "done"},
        }

    except Exception as e:
        logger.exception("Career Coach agent failed")
        return {
            "errors": [f"Career Coach agent failed: {str(e)}"],
            "agent_statuses": {"career_coach": "failed"},
        }


# Alias for graph.py compatibility
run = run_career_coach_agent
