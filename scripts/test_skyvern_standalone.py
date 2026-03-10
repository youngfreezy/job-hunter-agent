#!/usr/bin/env python3
# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Standalone test for Skyvern job application on ATS URLs.

Tests Skyvern's ability to navigate and fill forms on real ATS job pages
(Greenhouse, Lever) without the full pipeline.

Usage:
    # Test against production Skyvern (Railway internal)
    python scripts/test_skyvern_standalone.py --env production

    # Test against local Skyvern
    python scripts/test_skyvern_standalone.py --env local

    # Test a specific URL
    python scripts/test_skyvern_standalone.py --url https://boards.greenhouse.io/example/jobs/123
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("test_skyvern")

# Test ATS job URLs (real listings from MCP discovery)
TEST_URLS = [
    # Greenhouse
    "https://boards.greenhouse.io/samsara/jobs/7367490",
    # Lever
    "https://jobs.lever.co/traackr/6c3489c4-7677-4735-9137-10dc37c000f5",
]

# Fake user profile for testing
TEST_PROFILE = {
    "first_name": "Test",
    "last_name": "User",
    "full_name": "Test User",
    "email": "testuser@example.com",
    "phone": "555-0100",
    "location": "San Francisco, CA",
    "resume_text": "Experienced software engineer with 10 years of experience...",
}

ENVS = {
    "production": {
        "api_url": "http://skyvern.railway.internal:8080/api/v1",
        "api_key": os.environ.get("SKYVERN_API_KEY", ""),
    },
    "local": {
        "api_url": "http://localhost:8080/api/v1",
        "api_key": os.environ.get("SKYVERN_API_KEY", ""),
    },
    "cloud": {
        "api_url": "https://api.skyvern.com/api/v1",
        "api_key": os.environ.get("SKYVERN_API_KEY", ""),
    },
}

TERMINAL_STATUSES = {"completed", "failed", "terminated", "canceled", "timed_out"}


async def test_skyvern_task(
    api_url: str,
    api_key: str,
    job_url: str,
    timeout: int = 180,
) -> dict:
    """Create a Skyvern task and wait for it to complete."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key

    navigation_goal = (
        "Navigate to this job listing page. "
        "If there is an application form, fill it out with the provided information. "
        "Fill in: name, email, phone, location. "
        "For resume/CV upload fields, skip them (we are testing form navigation only). "
        "After filling required fields, click Submit/Apply. "
        "If the page asks to log in or create an account, STOP and report 'auth_required'. "
        "If the job is expired or not found, STOP and report 'job_expired'."
    )

    task_body = {
        "url": job_url,
        "navigation_goal": navigation_goal,
        "data_extraction_goal": (
            "Extract: 1) Whether the page shows a job application form, "
            "2) Any confirmation message after submission, "
            "3) Any error messages, "
            "4) Whether login/auth is required, "
            "5) Whether the job is expired"
        ),
        "navigation_payload": TEST_PROFILE,
        "extracted_information_schema": {
            "type": "object",
            "properties": {
                "has_application_form": {"type": "boolean"},
                "confirmation_message": {"type": "string"},
                "error_message": {"type": "string"},
                "auth_required": {"type": "boolean"},
                "job_expired": {"type": "boolean"},
                "page_title": {"type": "string"},
            },
        },
        "proxy_location": "RESIDENTIAL",
    }

    print(f"\n{'='*60}")
    print(f"Testing: {job_url}")
    print(f"{'='*60}")

    async with httpx.AsyncClient(timeout=30) as client:
        # Create task
        print("Creating Skyvern task...")
        try:
            resp = await client.post(
                f"{api_url}/tasks",
                json=task_body,
                headers=headers,
            )
            resp.raise_for_status()
            task_data = resp.json()
        except httpx.HTTPStatusError as e:
            print(f"FAIL: Task creation failed: {e.response.status_code}")
            print(f"  Response: {e.response.text[:500]}")
            return {"status": "creation_failed", "error": str(e)}
        except httpx.RequestError as e:
            print(f"FAIL: Connection error: {e}")
            return {"status": "connection_failed", "error": str(e)}

        task_id = task_data.get("task_id") or task_data.get("id") or task_data.get("run_id")
        print(f"Task created: {task_id}")

        # Poll for completion
        elapsed = 0
        status = "created"
        result_data = {}

        while elapsed < timeout and status not in TERMINAL_STATUSES:
            await asyncio.sleep(5)
            elapsed += 5

            try:
                poll_resp = await client.get(
                    f"{api_url}/tasks/{task_id}",
                    headers=headers,
                )
                poll_resp.raise_for_status()
                result_data = poll_resp.json()
                status = (result_data.get("status") or "unknown").lower()
                print(f"  [{elapsed}s] Status: {status}")
            except Exception as e:
                print(f"  [{elapsed}s] Poll error: {e}")

        # Results
        print(f"\nFinal status: {status}")
        extracted = result_data.get("extracted_information") or {}
        failure_reason = result_data.get("failure_reason") or ""
        screenshots = result_data.get("screenshot_urls") or []

        if extracted:
            print(f"Extracted info: {json.dumps(extracted, indent=2)}")
        if failure_reason:
            print(f"Failure reason: {failure_reason}")
        if screenshots:
            print(f"Screenshots ({len(screenshots)}):")
            for s in screenshots[-3:]:
                print(f"  {s}")

        return {
            "url": job_url,
            "status": status,
            "extracted": extracted,
            "failure_reason": failure_reason,
            "elapsed": elapsed,
            "task_id": task_id,
        }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="local", choices=ENVS.keys())
    parser.add_argument("--url", help="Test a specific URL instead of defaults")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--api-key", help="Skyvern API key (overrides env)")
    args = parser.parse_args()

    env = ENVS[args.env]
    api_url = env["api_url"]
    api_key = args.api_key or env["api_key"]

    urls = [args.url] if args.url else TEST_URLS

    print(f"Skyvern API: {api_url}")
    print(f"API key: {'set' if api_key else 'NOT SET'}")
    print(f"Testing {len(urls)} URL(s)")

    results = []
    for url in urls:
        result = await test_skyvern_task(api_url, api_key, url, args.timeout)
        results.append(result)

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for r in results:
        url = r.get("url", "?")
        status = r.get("status", "?")
        elapsed = r.get("elapsed", 0)
        failure = r.get("failure_reason", "")
        icon = "✓" if status == "completed" else "✗"
        print(f"  {icon} {url[:60]}...")
        print(f"    Status: {status} ({elapsed}s)")
        if failure:
            print(f"    Failure: {failure[:100]}")


if __name__ == "__main__":
    asyncio.run(main())
