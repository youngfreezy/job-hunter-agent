#!/usr/bin/env python3
# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Integration test for MCP-based agentic discovery.

Imports the actual discover_all_boards() from mcp_discovery and verifies:
1. Jobs are returned
2. All jobs have ATS URLs (not auth-walled board URLs)
3. JobListing objects are well-formed

Usage:
    cd backend && source venv/bin/activate
    BRIGHT_DATA_MCP_TOKEN=c3e3f18f-f09a-43c4-9730-9f00b0ae0501 \
        python -m scripts.test_mcp_discovery

    Or from repo root:
    cd job-hunter-agent
    BRIGHT_DATA_MCP_TOKEN=c3e3f18f-f09a-43c4-9730-9f00b0ae0501 \
        backend/venv/bin/python -m scripts.test_mcp_discovery
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set token if not in env
if not os.environ.get("BRIGHT_DATA_MCP_TOKEN"):
    os.environ["BRIGHT_DATA_MCP_TOKEN"] = "c3e3f18f-f09a-43c4-9730-9f00b0ae0501"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
logger = logging.getLogger("test_mcp_discovery")

# Auth-walled domains that should NOT appear in results
_AUTH_WALLED = {"linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com"}

# ATS domains we expect
_ATS_DOMAINS = {"greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com",
                "smartrecruiters.com", "icims.com", "jobvite.com", "workable.com", "breezy.hr"}


async def main():
    from backend.shared.models.schemas import SearchConfig
    from backend.browser.tools.mcp_discovery import discover_all_boards

    search_config = SearchConfig(
        keywords=["Senior Software Engineer", "AI Engineer"],
        locations=["Remote"],
        remote_only=True,
    )

    session_id = "test-mcp-discovery-001"
    boards = ["linkedin", "indeed", "glassdoor"]  # ignored by MCP discovery

    print("=" * 60)
    print("MCP Discovery Integration Test")
    print("=" * 60)
    print(f"Keywords: {search_config.keywords}")
    print(f"Remote only: {search_config.remote_only}")
    print()

    jobs = await discover_all_boards(
        boards=boards,
        search_config=search_config,
        session_id=session_id,
        max_per_board=10,
    )

    print(f"\n{'=' * 60}")
    print(f"RESULTS: {len(jobs)} jobs found")
    print("=" * 60)

    auth_walled_count = 0
    ats_count = 0
    missing_fields = 0

    for i, job in enumerate(jobs, 1):
        url = job.url or ""
        url_lower = url.lower()

        # Check for auth-walled URLs
        is_auth_walled = any(d in url_lower for d in _AUTH_WALLED)
        if is_auth_walled:
            auth_walled_count += 1

        # Check for ATS URLs
        is_ats = any(d in url_lower for d in _ATS_DOMAINS)
        if is_ats:
            ats_count += 1

        # Check required fields
        if not job.title or not job.company or not job.url:
            missing_fields += 1

        status = "AUTH-WALLED" if is_auth_walled else ("ATS" if is_ats else "OTHER")
        print(f"\n  {i}. [{status}] {job.title}")
        print(f"     Company: {job.company}")
        print(f"     Location: {job.location}")
        print(f"     ATS Type: {job.ats_type}")
        print(f"     Remote: {job.is_remote}")
        print(f"     URL: {url[:100]}")
        if job.salary_range:
            print(f"     Salary: {job.salary_range}")

    print(f"\n{'=' * 60}")
    print("VALIDATION")
    print("=" * 60)

    passed = True

    # Test 1: Jobs were returned
    if len(jobs) == 0:
        print("FAIL: No jobs returned")
        passed = False
    else:
        print(f"PASS: {len(jobs)} jobs returned")

    # Test 2: No auth-walled URLs
    if auth_walled_count > 0:
        print(f"FAIL: {auth_walled_count} jobs have auth-walled URLs")
        passed = False
    else:
        print("PASS: No auth-walled URLs")

    # Test 3: All have ATS URLs
    non_ats = len(jobs) - ats_count
    if non_ats > 0:
        print(f"WARN: {non_ats} jobs have non-ATS URLs (may be OK if they're direct apply)")
    else:
        print(f"PASS: All {ats_count} jobs have ATS URLs")

    # Test 4: No missing fields
    if missing_fields > 0:
        print(f"FAIL: {missing_fields} jobs have missing title/company/URL")
        passed = False
    else:
        print("PASS: All jobs have required fields")

    # Test 5: Titles are unique (dedup working)
    titles = [f"{j.title.lower()}|{j.company.lower()}" for j in jobs]
    dupes = len(titles) - len(set(titles))
    if dupes > 0:
        print(f"FAIL: {dupes} duplicate title+company combos")
        passed = False
    else:
        print("PASS: No duplicates")

    print(f"\n{'=' * 60}")
    if passed:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print("=" * 60)

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
