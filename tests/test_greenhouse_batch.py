"""Batch Greenhouse application test.

Discovers 20 Greenhouse jobs via the public API, then applies to each
using the full applier pipeline (form extraction → Claude analysis → fill → submit).
Target: at least 15/20 successful submissions.
"""

import asyncio
import logging
import os
import sys
import time

# Ensure backend imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
# Suppress noisy loggers
for name in ("httpx", "httpcore", "pypdf"):
    logging.getLogger(name).setLevel(logging.WARNING)

logger = logging.getLogger("batch_test")


async def main():
    from backend.browser.manager import BrowserManager
    from backend.browser.anti_detect.stealth import apply_stealth
    from backend.browser.tools.ats_detector import detect_ats_type
    from backend.browser.tools.appliers import get_applier
    from backend.shared.models.schemas import (
        ApplicationStatus, SearchConfig,
    )
    from backend.browser.tools.job_boards.greenhouse_boards import scrape_greenhouse_lever
    from pypdf import PdfReader

    # --- Resume ---
    resume_path = "/Users/janedoe/Desktop/Resumes/Jane_Doe_Resume_AI_Native_2026.pdf"
    reader = PdfReader(resume_path)
    resume_text = "\n".join(p.extract_text() for p in reader.pages)
    logger.info("Resume loaded: %d chars", len(resume_text))

    user_profile = {
        "name": "Jane Doe",
        "email": "jane.doe@example.com",
        "phone": "(555) 123-4567",
        "location": "Austin, TX",
    }

    cover_letter = (
        "I am excited to apply for this position. With extensive experience in "
        "AI-native application development, full-stack engineering with React/Next.js "
        "and Python/FastAPI, and building LLM-powered systems including agentic workflows "
        "and RAG pipelines, I believe I would be a strong addition to your team. "
        "I am passionate about building durable AI systems that augment human workflows."
    )

    # --- Discover ---
    config = SearchConfig(
        keywords=["Software Engineer", "AI Engineer", "Machine Learning", "Full Stack", "Data Engineer", "Platform Engineer"],
        locations=["Remote"],
        remote_only=True,
    )
    logger.info("Discovering Greenhouse jobs...")
    listings = await scrape_greenhouse_lever(None, config, max_results=20)
    logger.info("Found %d listings across %d companies",
                len(listings), len(set(l.company for l in listings)))

    if len(listings) < 10:
        logger.error("Not enough listings found (%d). Need at least 10.", len(listings))
        return

    # --- Apply ---
    manager = BrowserManager()
    await manager.start(headless=True)
    ctx_id, context = await manager.new_context()

    submitted = []
    failed = []
    skipped = []

    for i, job in enumerate(listings):
        logger.info(
            "\n%s\n[%d/%d] Applying: %s at %s\nURL: %s\n%s",
            "=" * 60, i + 1, len(listings), job.title, job.company, job.url, "=" * 60,
        )
        start = time.monotonic()
        page = await context.new_page()
        await apply_stealth(page)

        try:
            # Navigate
            await page.goto(job.url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(2)

            # Check for dead page
            page_text_len = await page.evaluate("() => document.body.innerText.length")
            if page_text_len < 100:
                logger.warning("Dead page — skipping")
                skipped.append((job, "dead_page"))
                continue

            # Detect ATS & get applier
            ats_type = await detect_ats_type(page)
            applier = get_applier(job.board.value, ats_type, page, "batch-test")

            # Apply
            result = await applier.apply(
                job=job,
                user_profile=user_profile,
                resume_text=resume_text,
                cover_letter=cover_letter,
                resume_file_path=resume_path,
            )

            elapsed = int(time.monotonic() - start)

            if result.status == ApplicationStatus.SUBMITTED:
                submitted.append((job, elapsed))
                logger.info("SUBMITTED in %ds: %s at %s", elapsed, job.title, job.company)
            elif result.status == ApplicationStatus.SKIPPED:
                skipped.append((job, result.error_message))
                logger.warning("SKIPPED: %s — %s", job.title, result.error_message)
            else:
                failed.append((job, result.error_message))
                logger.error("FAILED: %s — %s", job.title, result.error_message)

        except Exception as exc:
            elapsed = int(time.monotonic() - start)
            failed.append((job, str(exc)))
            logger.error("EXCEPTION after %ds: %s — %s", elapsed, job.title, exc)
        finally:
            if not page.is_closed():
                await page.close()

        # Cooldown between applications
        if i < len(listings) - 1:
            await asyncio.sleep(3)

    await manager.stop()

    # --- Report ---
    print("\n" + "=" * 60)
    print("BATCH APPLICATION REPORT")
    print("=" * 60)
    print(f"\nTotal:     {len(listings)}")
    print(f"Submitted: {len(submitted)}")
    print(f"Failed:    {len(failed)}")
    print(f"Skipped:   {len(skipped)}")
    print(f"Success rate: {len(submitted)}/{len(listings)} ({100*len(submitted)//len(listings)}%)")

    if submitted:
        print(f"\nSUBMITTED ({len(submitted)}):")
        for job, elapsed in submitted:
            print(f"  [{job.company}] {job.title} ({elapsed}s)")

    if failed:
        print(f"\nFAILED ({len(failed)}):")
        for job, error in failed:
            print(f"  [{job.company}] {job.title}: {error}")

    if skipped:
        print(f"\nSKIPPED ({len(skipped)}):")
        for job, reason in skipped:
            print(f"  [{job.company}] {job.title}: {reason}")

    target = 15
    if len(submitted) >= target:
        print(f"\nTARGET MET: {len(submitted)}/{len(listings)} >= {target}")
    else:
        print(f"\nTARGET MISSED: {len(submitted)}/{len(listings)} < {target}")


if __name__ == "__main__":
    asyncio.run(main())
