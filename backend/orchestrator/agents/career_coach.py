"""Career Coach Agent -- the emotional and strategic heart of JobHunter.

Analyses the user's resume, rewrites it like a salesperson pitching their best
client, coaches away impostor-syndrome language, drafts a master cover letter
template, offers LinkedIn advice, and scores the resume on five dimensions.

Uses the Anthropic SDK directly (not LangChain) for streaming so we can emit
real-time progress events to the frontend via SSE.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

import anthropic

from backend.orchestrator.pipeline.state import JobHunterState
from backend.shared.config import get_settings
from backend.shared.event_bus import emit_agent_event
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

# Progress milestones based on JSON key detection in the stream
_PROGRESS_KEYS = [
    ("rewritten_resume", "Rewriting your resume with stronger language..."),
    ("resume_score", "Scoring your original resume..."),
    ("cover_letter_template", "Drafting a master cover letter template..."),
    ("linkedin_advice", "Preparing LinkedIn profile advice..."),
    ("confidence_message", "Writing your confidence coaching message..."),
    ("key_strengths", "Identifying your key strengths..."),
    ("improvement_areas", "Noting areas for growth..."),
]


# ---------------------------------------------------------------------------
# Agent entry-point
# ---------------------------------------------------------------------------
async def run_career_coach_agent(state: JobHunterState) -> Dict[str, Any]:
    """Analyse resume, rewrite it, coach the user, and score the original.

    Uses Anthropic SDK streaming to emit real-time progress events so
    the user sees what the coach is working on instead of a blank wait.
    """
    session_id = state.get("session_id", "")

    try:
        settings = get_settings()
        client = anthropic.AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            max_retries=5,
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
            config_dict = (
                search_config.model_dump()
                if hasattr(search_config, "model_dump")
                else search_config.dict()
            )
            parts.append(
                f"Structured SearchConfig:\n{json.dumps(config_dict, indent=2)}"
            )

        user_message = "\n\n".join(parts)

        # -- Stream the LLM response ----------------------------------------
        await emit_agent_event(session_id, "coaching_progress", {
            "step": "Starting resume analysis...",
            "progress": 0,
        })

        raw_json = ""
        seen_keys: set[str] = set()
        char_count = 0

        async with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=6000,
            temperature=0,
            system=COACH_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            async for text in stream.text_stream:
                raw_json += text
                char_count += len(text)

                # Detect progress milestones as JSON keys appear in the stream
                for key, message in _PROGRESS_KEYS:
                    if key not in seen_keys and f'"{key}"' in raw_json:
                        seen_keys.add(key)
                        progress = int((len(seen_keys) / len(_PROGRESS_KEYS)) * 100)
                        await emit_agent_event(session_id, "coaching_progress", {
                            "step": message,
                            "progress": progress,
                        })

        await emit_agent_event(session_id, "coaching_progress", {
            "step": "Finalizing coach output...",
            "progress": 95,
        })

        # -- Clean up common LLM JSON issues --------------------------------
        if "```json" in raw_json:
            raw_json = raw_json.split("```json", 1)[1]
            raw_json = raw_json.rsplit("```", 1)[0]
        elif "```" in raw_json:
            raw_json = raw_json.split("```", 1)[1]
            raw_json = raw_json.rsplit("```", 1)[0]
        raw_json = raw_json.strip()

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

        await emit_agent_event(session_id, "coaching_progress", {
            "step": f"Resume scored {resume_score.overall}/100 — coaching complete!",
            "progress": 100,
        })

        return {
            "coach_output": coach_output,
            "coached_resume": coach_output.rewritten_resume,
            "cover_letter_template": coach_output.cover_letter_template,
            "status": "discovering",
            "agent_statuses": {"career_coach": "done"},
        }

    except Exception as e:
        logger.exception("Career Coach agent failed")
        await emit_agent_event(session_id, "coaching_progress", {
            "step": f"Coach encountered an error: {str(e)[:100]}",
            "progress": -1,
        })
        return {
            "errors": [f"Career Coach agent failed: {str(e)}"],
            "agent_statuses": {"career_coach": "failed"},
        }


# Alias for graph.py compatibility
run = run_career_coach_agent
