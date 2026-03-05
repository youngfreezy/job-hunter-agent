"""LinkedIn Profile Updater -- guided semi-automatic profile updates via browser-use.

Opens a visible browser to LinkedIn, waits for the user to log in, then
applies profile updates one section at a time using an AI agent.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from backend.shared.config import get_settings
from backend.shared.event_bus import emit_agent_event

logger = logging.getLogger(__name__)

# LinkedIn section update types and their nav instructions
SECTION_LABELS = {
    "headline": "Headline",
    "about": "About / Summary",
    "featured": "Featured Section",
    "skills": "Skills",
    "experience": "Work Experience",
    "education": "Education",
    "url": "Custom URL",
}


def _build_section_prompt(section: str, content: str, linkedin_url: Optional[str] = None) -> str:
    """Build a task prompt for updating a specific LinkedIn section."""

    profile_nav = (
        f"Navigate to {linkedin_url} to view the profile."
        if linkedin_url
        else "Click on 'Me' in the top nav, then 'View Profile'."
    )

    section_prompts = {
        "headline": f"""Update the LinkedIn profile headline.

1. {profile_nav}
2. Click the pencil/edit icon next to the name at the top of the profile (or click on the intro card to edit).
3. Find the "Headline" field in the edit popup/modal.
4. Clear the existing headline text.
5. Type this new headline exactly: {content}
6. Click "Save".
7. Verify the headline now shows the new text on the profile page.
""",
        "about": f"""Update the LinkedIn "About" section.

1. {profile_nav}
2. Scroll down to the "About" section.
3. Click the pencil/edit icon on the About section.
4. Clear the existing text in the About text area.
5. Paste this new About text:

{content}

6. Click "Save".
7. Verify the About section now shows the updated text.
""",
        "featured": f"""Add items to the LinkedIn "Featured" section.

1. {profile_nav}
2. If there's no Featured section, click "Add profile section" > "Recommended" > "Add featured".
3. If Featured exists, click the "+" button in the Featured section.
4. For each link/item described below, click "Add a link", paste the URL, add a title and description, then save.

Items to add:
{content}

5. Verify the Featured section shows the new items.
""",
        "skills": f"""Update LinkedIn Skills section.

1. {profile_nav}
2. Scroll down to the "Skills" section.
3. Click "Add a new skill" or the pencil/edit icon.
4. Add each of the following skills (search and select each one):

{content}

5. After adding all skills, reorder so the most relevant ones are in the top 3.
6. Save and verify.
""",
        "experience": f"""Update LinkedIn Work Experience entries.

1. {profile_nav}
2. Scroll to the "Experience" section.
3. For each entry below, click the pencil/edit icon on the matching position.
4. Update the description field with the new bullet points provided.
5. Save each entry.

Updates:
{content}

6. Verify the updated descriptions are visible.
""",
        "education": f"""Update LinkedIn Education section.

1. {profile_nav}
2. Scroll to the "Education" section.
3. Click the pencil/edit icon on the matching entry.
4. Update the description field:

{content}

5. Save and verify.
""",
        "url": f"""Customize the LinkedIn profile URL.

1. {profile_nav}
2. Click "Edit public profile & URL" in the right sidebar, or go to Settings > Visibility > Edit your public profile.
3. Click the pencil icon next to the current URL.
4. Change the custom URL to: {content}
5. Save and verify the new URL.
""",
    }

    base = section_prompts.get(section, f"Update the '{section}' section with:\n{content}")

    return f"""You are updating a LinkedIn profile. The user is already logged in.

IMPORTANT RULES:
- Do NOT navigate away from LinkedIn.
- Do NOT click "Sign Out" or modify any account settings.
- Work carefully and verify each change before moving to the next.
- If you encounter an error or modal blocker, report it and stop.
- Take screenshots after each major action to verify.

TASK:
{base}
"""


async def wait_for_login_signal(session_id: str, timeout: int = 300) -> bool:
    """Wait for the user to signal they've logged into LinkedIn.

    Polls a Redis key set by the frontend when the user clicks "I'm logged in".
    """
    import redis.asyncio as aioredis

    settings = get_settings()
    redis_client = aioredis.from_url(settings.REDIS_URL)

    key = f"linkedin:logged_in:{session_id}"
    try:
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            val = await redis_client.get(key)
            if val:
                await redis_client.delete(key)
                return True
            await asyncio.sleep(2)
        return False
    finally:
        await redis_client.close()


async def update_linkedin_profile(
    session_id: str,
    updates: List[Dict[str, str]],
    linkedin_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Update LinkedIn profile sections one at a time using browser-use.

    Parameters
    ----------
    session_id:
        For SSE event emission and Redis signaling.
    updates:
        List of dicts like [{"section": "headline", "content": "..."}, ...].
    linkedin_url:
        Optional LinkedIn profile URL for direct navigation.

    Returns
    -------
    Dict with results per section.
    """
    from browser_use import Agent, Browser, ChatAnthropic

    settings = get_settings()
    start_time = time.monotonic()
    results: List[Dict[str, Any]] = []

    # Always use headed mode so the user can see what's happening
    browser = Browser(headless=False, disable_security=True)

    try:
        # Step 1: Open LinkedIn and wait for the user to log in
        await emit_agent_event(session_id, "linkedin_update_progress", {
            "step": "Opening LinkedIn — please log in to your account...",
            "section": "login",
            "progress": 0,
        })

        # Navigate to LinkedIn login directly via Playwright (no AI agent needed)
        await browser.start()
        await browser.navigate_to("https://www.linkedin.com/login")

        llm = ChatAnthropic(
            model="claude-sonnet-4-5",
            api_key=settings.ANTHROPIC_API_KEY,
            max_tokens=4096,
        )

        await emit_agent_event(session_id, "linkedin_login_required", {
            "step": "LinkedIn is open — log in and click 'I'm logged in' when ready",
            "section": "login",
            "progress": 5,
        })

        # Wait for user to confirm login
        logged_in = await wait_for_login_signal(session_id, timeout=300)
        if not logged_in:
            await emit_agent_event(session_id, "linkedin_update_failed", {
                "step": "Timed out waiting for login confirmation",
                "section": "login",
                "error": "Login timeout — try again",
            })
            return {"success": False, "error": "Login timeout", "results": []}

        await emit_agent_event(session_id, "linkedin_update_progress", {
            "step": "Logged in! Starting profile updates...",
            "section": "login",
            "progress": 10,
        })

        # Step 2: Process each update section
        total = len(updates)
        for idx, update in enumerate(updates):
            section = update["section"]
            content = update["content"]
            section_label = SECTION_LABELS.get(section, section)

            base_pct = 10 + int((idx / total) * 85)

            await emit_agent_event(session_id, "linkedin_update_progress", {
                "step": f"Updating {section_label} ({idx + 1} of {total})...",
                "section": section,
                "progress": base_pct,
                "current": idx + 1,
                "total": total,
            })

            task_prompt = _build_section_prompt(section, content, linkedin_url)

            step_count = 0

            async def on_step_end(agent_instance):
                nonlocal step_count
                step_count += 1
                try:
                    actions = agent_instance.history.model_actions()
                    latest = str(actions[-1])[:300] if actions else "working..."
                    await emit_agent_event(session_id, "linkedin_browser_action", {
                        "section": section,
                        "step": step_count,
                        "action": latest,
                    })
                except Exception:
                    pass

            agent = Agent(
                task=task_prompt,
                llm=llm,
                browser=browser,
                max_actions_per_step=1,
                use_vision=True,
                max_failures=3,
            )

            try:
                result = await agent.run(max_steps=25, on_step_end=on_step_end)

                is_success = result.is_successful()
                final_text = str(result.final_result() or "").lower()
                if any(kw in final_text for kw in ["success", "updated", "saved", "verified"]):
                    is_success = True

                section_result = {
                    "section": section,
                    "label": section_label,
                    "success": is_success,
                    "error": None if is_success else final_text[:200],
                }
                results.append(section_result)

                status = "done" if is_success else "had issues"
                await emit_agent_event(session_id, "linkedin_update_progress", {
                    "step": f"{section_label}: {status}",
                    "section": section,
                    "progress": base_pct + int(85 / total),
                    "success": is_success,
                })

            except Exception as exc:
                logger.exception("LinkedIn update failed for section %s", section)
                results.append({
                    "section": section,
                    "label": section_label,
                    "success": False,
                    "error": str(exc)[:200],
                })
                await emit_agent_event(session_id, "linkedin_update_progress", {
                    "step": f"{section_label}: failed — {str(exc)[:100]}",
                    "section": section,
                    "progress": base_pct + int(85 / total),
                    "success": False,
                })

            # Small cooldown between sections to avoid detection
            if idx < total - 1:
                await asyncio.sleep(3)

        # Step 3: Summary
        succeeded = sum(1 for r in results if r["success"])
        failed = total - succeeded
        duration = int(time.monotonic() - start_time)

        await emit_agent_event(session_id, "linkedin_update_complete", {
            "step": f"All done — {succeeded} updated, {failed} need attention",
            "progress": 100,
            "results": results,
            "duration": duration,
        })

        return {
            "success": failed == 0,
            "results": results,
            "succeeded": succeeded,
            "failed": failed,
            "duration_seconds": duration,
        }

    except Exception as exc:
        logger.exception("LinkedIn updater failed")
        await emit_agent_event(session_id, "linkedin_update_failed", {
            "step": f"Something went wrong: {str(exc)[:200]}",
            "error": str(exc),
        })
        return {
            "success": False,
            "error": str(exc),
            "results": results,
            "duration_seconds": int(time.monotonic() - start_time),
        }

    finally:
        try:
            await browser.stop()
        except Exception:
            pass
