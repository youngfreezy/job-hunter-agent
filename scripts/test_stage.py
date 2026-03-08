#!/usr/bin/env python3
# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Test individual pipeline stages without running the full pipeline.

Usage:
    # Activate venv first
    source backend/venv/bin/activate

    # Test LLM connectivity + retry (just calls Claude with a tiny prompt)
    python scripts/test_stage.py llm

    # Test browser headed mode (opens a browser window)
    python scripts/test_stage.py browser

    # Test intake agent with sample data
    python scripts/test_stage.py intake

    # Test career coach with sample data
    python scripts/test_stage.py coach

    # Test discovery with sample search config (scrapes 1 board)
    python scripts/test_stage.py discovery

    # Test the full pipeline from a fresh session via the API
    python scripts/test_stage.py pipeline
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import os

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


SAMPLE_RESUME = """John Doe
john.doe@example.com | (555) 123-4567 | San Francisco, CA

SUMMARY
Senior Software Engineer with 8 years of experience in Python, TypeScript,
and cloud infrastructure. Specializing in distributed systems and ML pipelines.

EXPERIENCE
Senior Software Engineer | Acme Corp | 2021 - Present
- Built real-time data pipeline processing 10M events/day
- Led migration from monolith to microservices (Python/FastAPI)

Software Engineer | StartupXYZ | 2018 - 2021
- Developed React/TypeScript frontend for B2B SaaS platform
- Implemented CI/CD pipelines reducing deploy time by 70%

EDUCATION
B.S. Computer Science | UC Berkeley | 2016
"""


async def test_llm():
    """Test LLM connectivity and retry behavior."""
    from backend.shared.llm import build_llm, invoke_with_retry, SONNET_MODEL, HAIKU_MODEL

    print(f"Testing LLM connectivity...")
    print(f"  Sonnet model: {SONNET_MODEL}")
    print(f"  Haiku model:  {HAIKU_MODEL}")

    # Test with Haiku (cheaper, faster)
    llm = build_llm(model=HAIKU_MODEL, max_tokens=100)
    print(f"\n1. Direct invoke (Haiku, max_tokens=100)...")
    start = time.time()
    try:
        resp = await llm.ainvoke("Say 'hello' and nothing else.")
        print(f"   OK in {time.time()-start:.1f}s: {resp.content[:100]}")
    except Exception as e:
        print(f"   FAILED in {time.time()-start:.1f}s: {e}")

    # Test invoke_with_retry
    print(f"\n2. invoke_with_retry (Haiku)...")
    start = time.time()
    try:
        resp = await invoke_with_retry(llm, "Say 'retry test passed' and nothing else.")
        print(f"   OK in {time.time()-start:.1f}s: {resp.content[:100]}")
    except Exception as e:
        print(f"   FAILED in {time.time()-start:.1f}s: {e}")

    # Test with Sonnet
    llm_sonnet = build_llm(model=SONNET_MODEL, max_tokens=100)
    print(f"\n3. Direct invoke (Sonnet, max_tokens=100)...")
    start = time.time()
    try:
        resp = await llm_sonnet.ainvoke("Say 'sonnet ok' and nothing else.")
        print(f"   OK in {time.time()-start:.1f}s: {resp.content[:100]}")
    except Exception as e:
        print(f"   FAILED in {time.time()-start:.1f}s: {e}")

    print("\nLLM test complete.")


async def test_browser():
    """Test browser opens in headed mode."""
    from backend.browser.manager import BrowserManager

    print("Testing browser (headed mode)...")
    mgr = BrowserManager()
    await mgr.start(headless=False)
    print(f"  Browser running: {mgr.is_running}")

    ctx_id, page = await mgr.new_stealth_page()
    print(f"  Context: {ctx_id}")
    print("  Navigating to example.com...")
    await page.goto("https://example.com", wait_until="domcontentloaded")
    title = await page.title()
    print(f"  Page title: {title}")

    print("  Browser window should be visible. Closing in 5s...")
    await asyncio.sleep(5)

    await mgr.close_context(ctx_id)
    await mgr.stop()
    print("Browser test complete.")


async def test_intake():
    """Test intake agent with sample data."""
    from backend.orchestrator.agents.intake import run as run_intake

    print("Testing intake agent...")
    state = {
        "session_id": "test-intake",
        "user_id": "test",
        "keywords": ["software engineer", "python"],
        "locations": ["San Francisco, CA"],
        "remote_only": True,
        "salary_min": 150000,
        "resume_text": SAMPLE_RESUME,
        "preferences": {},
    }
    start = time.time()
    try:
        result = await run_intake(state)
        print(f"  OK in {time.time()-start:.1f}s")
        if result.get("search_config"):
            sc = result["search_config"]
            print(f"  Search config: {sc}")
        print(f"  Agent status: {result.get('agent_statuses', {})}")
    except Exception as e:
        print(f"  FAILED in {time.time()-start:.1f}s: {e}")


async def test_coach():
    """Test career coach agent."""
    from backend.orchestrator.agents.career_coach import run as run_coach

    print("Testing career coach agent...")
    state = {
        "session_id": "test-coach",
        "user_id": "test",
        "keywords": ["software engineer", "python"],
        "locations": ["San Francisco, CA"],
        "remote_only": True,
        "resume_text": SAMPLE_RESUME,
        "preferences": {},
    }
    start = time.time()
    try:
        result = await run_coach(state)
        elapsed = time.time() - start
        print(f"  OK in {elapsed:.1f}s")
        if result.get("coach_output"):
            co = result["coach_output"]
            print(f"  Score: {getattr(co, 'overall_score', 'N/A')}")
            print(f"  Coached resume length: {len(result.get('coached_resume', ''))}")
            print(f"  Cover letter template length: {len(result.get('cover_letter_template', ''))}")
        print(f"  Agent status: {result.get('agent_statuses', {})}")
    except Exception as e:
        print(f"  FAILED in {time.time()-start:.1f}s: {e}")


async def test_pipeline():
    """Test the full pipeline by creating a session via the API."""
    import httpx

    base = "http://localhost:8000"
    print("Testing full pipeline via API...")
    print(f"  Backend: {base}")

    # Check backend is running
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{base}/health", timeout=5)
            print(f"  Health: {r.status_code}")
    except Exception as e:
        print(f"  Backend not reachable: {e}")
        print("  Start the app with `npm start` first.")
        return

    # Create session
    payload = {
        "keywords": ["software engineer", "python"],
        "locations": ["San Francisco, CA"],
        "remote_only": True,
        "salary_min": 150000,
        "resume_text": SAMPLE_RESUME,
    }

    async with httpx.AsyncClient() as client:
        print("\n  Creating session...")
        r = await client.post(f"{base}/api/sessions", json=payload, timeout=30)
        if r.status_code != 200:
            print(f"  FAILED: {r.status_code} {r.text[:200]}")
            return
        data = r.json()
        session_id = data["session_id"]
        print(f"  Session: {session_id}")

        # Stream SSE events for up to 3 minutes
        print(f"\n  Streaming events (Ctrl+C to stop)...")
        print(f"  ---")
        try:
            async with client.stream(
                "GET", f"{base}/api/sessions/{session_id}/stream", timeout=180
            ) as stream:
                async for line in stream.aiter_lines():
                    if line.startswith("data:"):
                        try:
                            evt = json.loads(line[5:].strip())
                            agent = evt.get("agent", "?")
                            event = evt.get("event", "?")
                            msg = evt.get("data", {})
                            if isinstance(msg, dict):
                                msg = msg.get("step") or msg.get("message") or msg.get("stage") or str(msg)[:80]
                            print(f"  [{agent}] {event}: {str(msg)[:120]}")
                            if event == "done":
                                break
                        except json.JSONDecodeError:
                            pass
        except KeyboardInterrupt:
            print("\n  Stopped by user.")
        except Exception as e:
            print(f"\n  Stream ended: {e}")

    print("\nPipeline test complete.")


TESTS = {
    "llm": test_llm,
    "browser": test_browser,
    "intake": test_intake,
    "coach": test_coach,
    "pipeline": test_pipeline,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in TESTS:
        print(f"Usage: python {sys.argv[0]} <{'|'.join(TESTS.keys())}>")
        sys.exit(1)

    test_name = sys.argv[1]
    print(f"{'='*60}")
    print(f"  JobHunter Test: {test_name}")
    print(f"{'='*60}\n")
    asyncio.run(TESTS[test_name]())


if __name__ == "__main__":
    main()
