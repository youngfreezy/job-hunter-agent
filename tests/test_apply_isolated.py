# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Isolated apply test -- test the application flow with real job URLs.

Usage:
    cd <project_root>
    source backend/venv/bin/activate
    python -m tests.test_apply_isolated

Tests _apply_to_job() directly with a BrowserManager context,
bypassing the full LangGraph pipeline. One job per board.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from uuid import uuid4

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.browser.manager import BrowserManager
from backend.shared.models.schemas import (
    ApplicationResult,
    ApplicationStatus,
    JobBoard,
    JobListing,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger("test_apply_isolated")

# ---------------------------------------------------------------------------
# Test job URLs -- replace with fresh URLs from discovery logs as needed
# ---------------------------------------------------------------------------

TEST_JOBS = [
    JobListing(
        id=str(uuid4()),
        title="React Front End Developer",
        company="OptiBPO",
        location="Remote",
        url="https://www.linkedin.com/jobs/view/react-front-end-developer-at-optibpo-4377350376",
        board=JobBoard.LINKEDIN,
    ),
    JobListing(
        id=str(uuid4()),
        title="Senior Software Engineer",
        company="Example Corp",
        location="Remote",
        url="https://www.indeed.com/viewjob?jk=b92e48af5b4b48d4",
        board=JobBoard.INDEED,
    ),
    JobListing(
        id=str(uuid4()),
        title="Senior AI Engineer",
        company="Texas Sports Academy",
        location="Remote",
        url="https://www.glassdoor.com/job-listing/senior-ai-engineer-llm-systems-rag-optimization-texas-sports-academy-JV_KO0,47_KE48,68.htm?jl=1010034099048",
        board=JobBoard.GLASSDOOR,
    ),
]

# ---------------------------------------------------------------------------
# Minimal state dict (mimics what the graph would pass)
# ---------------------------------------------------------------------------

SAMPLE_RESUME = """Jane Doe
jane.doe@example.com
(555) 123-4567
San Francisco, CA

Senior Software Engineer with 8+ years of experience building web applications
using React, TypeScript, Python, and cloud infrastructure. Passionate about
AI/ML and building developer tools.

EXPERIENCE
- Senior Software Engineer at TechCo (2020-present)
  - Led migration of monolith to microservices, reducing deploy time by 60%
  - Built real-time data pipeline processing 1M+ events/day
- Software Engineer at StartupXYZ (2017-2020)
  - Full-stack development with React, Node.js, PostgreSQL
  - Implemented CI/CD pipeline reducing release cycle from 2 weeks to 2 days

SKILLS
Python, TypeScript, React, Next.js, FastAPI, PostgreSQL, Redis, Docker, AWS, GCP
"""

MINIMAL_STATE = {
    "session_id": f"test-apply-{uuid4().hex[:8]}",
    "resume_text": SAMPLE_RESUME,
    "coached_resume": SAMPLE_RESUME,
    "cover_letter_template": "Dear Hiring Manager,\n\nI am excited to apply for the {title} position at {company}...",
    "discovered_jobs": TEST_JOBS,
    "scored_jobs": [],
    "application_queue": [j.id for j in TEST_JOBS],
}


# ---------------------------------------------------------------------------
# Run one apply attempt
# ---------------------------------------------------------------------------

async def test_apply_single(job: JobListing) -> ApplicationResult:
    """Apply to a single job using the real apply pipeline."""
    from backend.orchestrator.agents.application import _apply_to_job

    session_id = MINIMAL_STATE["session_id"]
    manager = BrowserManager()

    logger.info("=" * 70)
    logger.info("TESTING: %s @ %s (%s)", job.title, job.company, job.board.value)
    logger.info("URL: %s", job.url)
    logger.info("=" * 70)

    try:
        # Start browser
        await manager.start_for_task(
            board=job.board,
            purpose="apply",
            headless=True,
        )
        _, context = await manager.new_context()

        result = await _apply_to_job(
            job_id=job.id,
            job=job,
            state=MINIMAL_STATE,
            session_id=session_id,
            context=context,
        )

        logger.info(
            "RESULT: %s — status=%s error=%s duration=%ss",
            job.title,
            result.status.value,
            result.error_message or "none",
            result.duration_seconds,
        )
        return result

    except Exception as exc:
        logger.error("EXCEPTION applying to %s: %s", job.title, exc, exc_info=True)
        return ApplicationResult(
            job_id=job.id,
            status=ApplicationStatus.FAILED,
            error_message=str(exc),
        )
    finally:
        try:
            await manager.stop()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    logger.info("Starting isolated apply test with %d jobs", len(TEST_JOBS))

    results: list[ApplicationResult] = []
    for job in TEST_JOBS:
        result = await test_apply_single(job)
        results.append(result)
        logger.info("")

    # Summary
    logger.info("=" * 70)
    logger.info("SUMMARY")
    logger.info("=" * 70)
    for job, result in zip(TEST_JOBS, results):
        logger.info(
            "  [%s] %s @ %s — %s%s",
            job.board.value,
            job.title,
            job.company,
            result.status.value,
            f" ({result.error_message})" if result.error_message else "",
        )

    submitted = sum(1 for r in results if r.status == ApplicationStatus.SUBMITTED)
    failed = sum(1 for r in results if r.status == ApplicationStatus.FAILED)
    skipped = sum(1 for r in results if r.status == ApplicationStatus.SKIPPED)
    logger.info("")
    logger.info("Submitted: %d | Failed: %d | Skipped: %d", submitted, failed, skipped)


if __name__ == "__main__":
    asyncio.run(main())
