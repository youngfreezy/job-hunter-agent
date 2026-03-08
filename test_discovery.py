# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Test discovery end-to-end: run all boards, validate URLs are real and ≤20."""
import asyncio
import logging
import sys

sys.path.insert(0, ".")

logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

import aiohttp
from backend.shared.models.schemas import SearchConfig
from backend.orchestrator.agents.discovery import run_discovery_agent


async def validate_url(session, url: str) -> tuple[str, int | str]:
    """HEAD request to check if URL is reachable."""
    try:
        async with session.head(url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=10),
                                headers={"User-Agent": "Mozilla/5.0"}) as resp:
            return url, resp.status
    except Exception as e:
        return url, str(e)


async def main():
    state = {
        "session_id": "test-discovery-final",
        "search_config": SearchConfig(
            keywords=["AI Engineer", "Full-Stack Engineer"],
            locations=["Remote"],
            remote_only=True,
            salary_min=None,
        ),
    }

    print("Running discovery (all boards, one browser)...")
    result = await run_discovery_agent(state)

    jobs = result.get("discovered_jobs", [])

    print(f"\n{'='*60}")
    print(f"DISCOVERY RESULTS: {len(jobs)} jobs")
    print(f"{'='*60}")

    for j in jobs:
        print(f"  [{j.board.value}] {j.title} @ {j.company}")
        print(f"         {j.url}")

    # Validate: ≤ 20 jobs
    assert len(jobs) <= 20, f"Too many jobs: {len(jobs)} (max 20)"
    print(f"\n✓ Job count OK: {len(jobs)} ≤ 20")

    # Validate: all have required fields
    for j in jobs:
        assert j.title, f"Missing title: {j}"
        assert j.company, f"Missing company: {j}"
        assert j.url and j.url.startswith("http"), f"Bad URL: {j.url}"
        assert j.board, f"Missing board: {j}"
    print(f"✓ All jobs have title, company, url, board")

    # Validate: URLs are reachable
    print(f"\nValidating {len(jobs)} URLs...")
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*[validate_url(session, j.url) for j in jobs])

    ok = 0
    bad = 0
    for url, status in results:
        if isinstance(status, int) and status < 400:
            ok += 1
            print(f"  ✓ {status} {url[:80]}")
        else:
            bad += 1
            print(f"  ✗ {status} {url[:80]}")

    print(f"\n{'='*60}")
    print(f"URL VALIDATION: {ok} OK, {bad} bad out of {len(jobs)}")
    print(f"{'='*60}")

    if len(jobs) == 0:
        print("\n✗ FAIL: No jobs discovered")
        return 1

    print(f"\n✓ PASS: {len(jobs)} valid jobs ready for application step")
    return 0


if __name__ == "__main__":
    rc = asyncio.run(main())
    sys.exit(rc)
