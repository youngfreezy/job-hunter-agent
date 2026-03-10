# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Skyvern-powered job application applier.

Sends job application tasks to a self-hosted Skyvern instance via REST API.
Skyvern uses visual AI (no hardcoded selectors) to navigate forms, fill fields,
upload files, and submit applications on any ATS platform.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

import httpx

from backend.shared.config import get_settings
from backend.shared.models.schemas import (
    ApplicationResult,
    ApplicationStatus,
    JobListing,
)

logger = logging.getLogger(__name__)

# Terminal statuses from Skyvern API
_TERMINAL_STATUSES = {"completed", "failed", "terminated", "canceled", "timed_out"}
_SUCCESS_STATUSES = {"completed"}

# Poll interval when waiting for task completion
_POLL_INTERVAL_SECONDS = 5


def _build_navigation_goal(
    job: JobListing,
    user_profile: Dict[str, str],
    cover_letter: str,
    has_credentials: bool = False,
) -> str:
    """Build a natural-language navigation goal for Skyvern."""
    parts = [
        f"Apply for the job '{job.title}' at '{job.company}'.",
        "Fill out the entire application form with the provided information.",
    ]
    if cover_letter:
        parts.append(
            "If there is a cover letter field or text area, paste the provided cover letter."
        )
    parts.append(
        "After filling all required fields, click the Submit/Apply button."
    )
    if has_credentials:
        parts.append(
            "If the page asks you to log in, use the provided board_username and "
            "board_password credentials to sign in, then continue with the application."
        )
    else:
        parts.append(
            "If the page asks you to create an account or log in, STOP and report "
            "'auth_required' as the failure reason."
        )
    parts.append(
        "If the job listing is expired or no longer available, STOP and report "
        "'job_expired' as the failure reason."
    )
    return " ".join(parts)


def _build_navigation_payload(
    user_profile: Dict[str, str],
    resume_text: str,
    cover_letter: str,
    resume_file_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the navigation_payload with user data for form filling."""
    payload: Dict[str, Any] = {}

    if user_profile.get("name"):
        # Split name into first/last for common form patterns
        name_parts = user_profile["name"].strip().split(" ", 1)
        payload["first_name"] = name_parts[0]
        payload["last_name"] = name_parts[1] if len(name_parts) > 1 else ""
        payload["full_name"] = user_profile["name"]

    if user_profile.get("email"):
        payload["email"] = user_profile["email"]
    if user_profile.get("phone"):
        payload["phone"] = user_profile["phone"]
    if user_profile.get("location"):
        payload["location"] = user_profile["location"]

    if resume_text:
        # Truncate for payload size limits (Skyvern sends this to LLM)
        payload["resume_text"] = resume_text[:4000]
    if cover_letter:
        payload["cover_letter"] = cover_letter
    if resume_file_url:
        payload["resume_url"] = resume_file_url

    return payload


async def apply_with_skyvern(
    job: JobListing,
    user_profile: Dict[str, str],
    resume_text: str,
    cover_letter: str,
    resume_file_path: Optional[str],
    session_id: str,
    board_credentials: Optional[Dict[str, Dict[str, str]]] = None,
) -> ApplicationResult:
    """Apply to a job using Skyvern's visual AI agent.

    1. POST a task to the Skyvern API with the job URL + user data
    2. Poll for completion
    3. Parse result into ApplicationResult
    """
    settings = get_settings()
    base_url = settings.SKYVERN_API_URL.rstrip("/")
    timeout = settings.SKYVERN_TASK_TIMEOUT

    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if settings.SKYVERN_API_KEY:
        headers["x-api-key"] = settings.SKYVERN_API_KEY

    # Check for saved credentials for this job's board
    board_name = job.board.value if hasattr(job.board, "value") else str(job.board)
    board_creds = (board_credentials or {}).get(board_name)
    has_credentials = bool(board_creds)

    # Build task request
    navigation_goal = _build_navigation_goal(job, user_profile, cover_letter, has_credentials=has_credentials)
    navigation_payload = _build_navigation_payload(
        user_profile=user_profile,
        resume_text=resume_text,
        cover_letter=cover_letter,
        resume_file_url=None,  # TODO: serve resume via signed URL
    )

    # Add board login credentials to payload if available
    if board_creds:
        navigation_payload["board_username"] = board_creds.get("username", "")
        navigation_payload["board_password"] = board_creds.get("password", "")
        logger.info("Skyvern: including %s credentials for authentication", board_name)

    task_body = {
        "url": job.url,
        "navigation_goal": navigation_goal,
        "data_extraction_goal": (
            "Extract any confirmation message, confirmation number, "
            "or application ID shown after submission. "
            "Also extract any error messages visible on the page."
        ),
        "navigation_payload": navigation_payload,
        "extracted_information_schema": {
            "type": "object",
            "properties": {
                "confirmation_message": {"type": "string"},
                "confirmation_id": {"type": "string"},
                "error_message": {"type": "string"},
                "auth_required": {"type": "boolean"},
                "job_expired": {"type": "boolean"},
            },
        },
        "proxy_location": "RESIDENTIAL",
    }

    logger.info(
        "Skyvern: creating task for %s @ %s — url=%s",
        job.title, job.company, job.url,
    )

    async with httpx.AsyncClient(timeout=30) as client:
        # --- Create task ---
        try:
            resp = await client.post(
                f"{base_url}/tasks",
                json=task_body,
                headers=headers,
            )
            resp.raise_for_status()
            task_data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("Skyvern task creation failed: %s %s", e.response.status_code, e.response.text[:500])
            return ApplicationResult(
                job_id=str(job.id),
                status=ApplicationStatus.FAILED,
                error_message=f"Skyvern API error: {e.response.status_code}",
            )
        except httpx.RequestError as e:
            logger.error("Skyvern connection error: %s", e)
            return ApplicationResult(
                job_id=str(job.id),
                status=ApplicationStatus.FAILED,
                error_message=f"Skyvern connection error: {e}",
            )

        task_id = task_data.get("task_id") or task_data.get("id") or task_data.get("run_id")
        if not task_id:
            logger.error("Skyvern returned no task ID: %s", task_data)
            return ApplicationResult(
                job_id=str(job.id),
                status=ApplicationStatus.FAILED,
                error_message="Skyvern returned no task ID",
            )

        logger.info("Skyvern task created: %s", task_id)

        # --- Poll for completion ---
        elapsed = 0
        status = "created"
        result_data: Dict[str, Any] = {}

        while elapsed < timeout and status not in _TERMINAL_STATUSES:
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            elapsed += _POLL_INTERVAL_SECONDS

            try:
                poll_resp = await client.get(
                    f"{base_url}/tasks/{task_id}",
                    headers=headers,
                )
                poll_resp.raise_for_status()
                result_data = poll_resp.json()
                status = (result_data.get("status") or "unknown").lower()
                logger.debug(
                    "Skyvern task %s: status=%s (elapsed=%ds)",
                    task_id, status, elapsed,
                )
            except Exception as poll_err:
                logger.warning("Skyvern poll error (will retry): %s", poll_err)
                continue

        # --- Parse result ---
        if status not in _TERMINAL_STATUSES:
            logger.warning("Skyvern task %s timed out after %ds", task_id, timeout)
            return ApplicationResult(
                job_id=str(job.id),
                status=ApplicationStatus.FAILED,
                error_message=f"Skyvern task timed out after {timeout}s",
                duration_seconds=elapsed,
            )

        extracted = result_data.get("extracted_information") or {}
        failure_reason = result_data.get("failure_reason") or ""
        screenshot_urls = result_data.get("screenshot_urls") or []
        last_screenshot = screenshot_urls[-1] if screenshot_urls else None

        if status in _SUCCESS_STATUSES:
            # Check extracted data for false positives
            if extracted.get("auth_required"):
                return ApplicationResult(
                    job_id=str(job.id),
                    status=ApplicationStatus.SKIPPED,
                    error_message="auth_required",
                    screenshot_url=last_screenshot,
                    duration_seconds=elapsed,
                )
            if extracted.get("job_expired"):
                return ApplicationResult(
                    job_id=str(job.id),
                    status=ApplicationStatus.SKIPPED,
                    error_message="job_expired",
                    screenshot_url=last_screenshot,
                    duration_seconds=elapsed,
                )

            confirmation = extracted.get("confirmation_message") or ""
            logger.info(
                "Skyvern task %s completed — confirmation: %s",
                task_id, confirmation[:200] if confirmation else "(none)",
            )
            return ApplicationResult(
                job_id=str(job.id),
                status=ApplicationStatus.SUBMITTED,
                cover_letter_used=cover_letter or None,
                screenshot_url=last_screenshot,
                duration_seconds=elapsed,
            )
        else:
            # Failed/terminated/canceled
            error_msg = failure_reason or extracted.get("error_message") or f"Skyvern status: {status}"
            logger.warning(
                "Skyvern task %s failed: %s", task_id, error_msg[:300],
            )
            return ApplicationResult(
                job_id=str(job.id),
                status=ApplicationStatus.FAILED,
                error_message=error_msg[:500],
                screenshot_url=last_screenshot,
                duration_seconds=elapsed,
            )
