"""Application Agent -- submits job applications (Phase 1 stub).

Phase 1:  Simulates application submission with mock results.
Phase 2:  Will use Playwright to fill real ATS forms.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List

from backend.orchestrator.pipeline.state import JobHunterState
from backend.shared.config import get_settings  # noqa: F401 – reserved for Phase 2
from backend.shared.models.schemas import ApplicationResult, ApplicationStatus

logger = logging.getLogger(__name__)

# Circuit-breaker threshold
MAX_CONSECUTIVE_FAILURES = 3


async def run_application_agent(state: JobHunterState) -> dict:
    """Iterate through the application queue and simulate submissions.

    In Phase 1, every application is marked as *submitted* with a mock
    screenshot URL.  A simple circuit breaker pauses the agent after
    ``MAX_CONSECUTIVE_FAILURES`` consecutive failures.

    Returns
    -------
    dict
        Keys: applications_submitted, applications_failed,
              consecutive_failures, status, agent_statuses, errors
    """
    errors: List[str] = []
    submitted: List[ApplicationResult] = []
    failed: List[ApplicationResult] = []
    consecutive_failures: int = state.get("consecutive_failures", 0)

    try:
        application_queue: List[str] = state.get("application_queue", [])
        if not application_queue:
            return {
                "applications_submitted": [],
                "applications_failed": [],
                "consecutive_failures": consecutive_failures,
                "status": "applying",
                "agent_statuses": {
                    "application": "completed -- nothing in queue"
                },
                "errors": [],
            }

        logger.info(
            "Application agent starting -- %d jobs in queue", len(application_queue)
        )

        for job_id in application_queue:
            # --- Circuit breaker ---
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                logger.warning(
                    "Circuit breaker tripped after %d consecutive failures -- pausing",
                    consecutive_failures,
                )
                return {
                    "applications_submitted": submitted,
                    "applications_failed": failed,
                    "consecutive_failures": consecutive_failures,
                    "status": "paused",
                    "agent_statuses": {
                        "application": (
                            f"paused -- circuit breaker after "
                            f"{consecutive_failures} consecutive failures"
                        )
                    },
                    "errors": errors,
                }

            try:
                # ----- Phase 1 stub: simulate a successful submission -----
                mock_screenshot = (
                    f"https://storage.jobhunter.dev/screenshots/"
                    f"{uuid.uuid4().hex[:12]}.png"
                )

                result = ApplicationResult(
                    job_id=job_id,
                    status=ApplicationStatus.SUBMITTED,
                    screenshot_url=mock_screenshot,
                    submitted_at=datetime.now(timezone.utc),
                    duration_seconds=3,
                )
                submitted.append(result)
                consecutive_failures = 0  # reset on success

                logger.info("Simulated submission for job %s", job_id)

            except Exception as exc:
                error_msg = f"Application failed for job {job_id}: {exc}"
                logger.error(error_msg)
                errors.append(error_msg)

                fail_result = ApplicationResult(
                    job_id=job_id,
                    status=ApplicationStatus.FAILED,
                    error_message=str(exc),
                )
                failed.append(fail_result)
                consecutive_failures += 1

        agent_status = (
            f"completed -- {len(submitted)} submitted, {len(failed)} failed"
        )

    except Exception as exc:
        logger.exception("Application agent failed")
        errors.append(f"Application agent error: {exc}")
        agent_status = f"failed -- {exc}"

    return {
        "applications_submitted": submitted,
        "applications_failed": failed,
        "consecutive_failures": consecutive_failures,
        "status": "applying",
        "agent_statuses": {"application": agent_status},
        "errors": errors,
    }
