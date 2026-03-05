"""End-to-end test: Sign in, create a session via the wizard, monitor pipeline progress.

Uses Playwright (from the backend venv) in headed mode with screenshots.
"""

import asyncio
import time
from pathlib import Path
from playwright.async_api import async_playwright

SCREENSHOTS_DIR = Path(__file__).parent / "test_screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)

BASE_URL = "http://localhost:3000"

# Test data
KEYWORDS = "software engineer, python developer, backend engineer"
LOCATIONS = "San Francisco, Remote"
RESUME_TEXT = """John Smith
Senior Software Engineer | Python, Go, TypeScript

EXPERIENCE
Senior Software Engineer — Acme Corp (2021–Present)
- Built scalable microservices handling 10M+ requests/day using Python and Go
- Led migration from monolith to event-driven architecture (Kafka, Redis)
- Mentored 4 junior engineers; established code review practices

Software Engineer — TechStart Inc (2018–2021)
- Developed REST APIs and GraphQL services using FastAPI and Django
- Implemented CI/CD pipelines reducing deployment time by 70%
- Built real-time data pipeline processing 500K events/hour

EDUCATION
B.S. Computer Science — UC Berkeley (2018)

SKILLS
Python, Go, TypeScript, PostgreSQL, Redis, Kafka, Docker, Kubernetes, AWS, GCP
FastAPI, Django, React, Next.js, GraphQL, REST APIs
"""


async def screenshot(page, name: str):
    path = SCREENSHOTS_DIR / f"{name}.png"
    await page.screenshot(path=str(path), full_page=True)
    print(f"  [screenshot] {path}")


async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=300)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        # ---- Step 1: Sign in ----
        print("1. Signing in...")
        await page.goto(f"{BASE_URL}/auth/login", wait_until="networkidle")
        # Wait for React hydration — Formik needs JS to be loaded
        await page.wait_for_selector('#email', timeout=15000)
        await page.wait_for_timeout(1000)
        await screenshot(page, "01_login")

        await page.fill('#email', "test@example.com")
        await page.fill('#password', "password123")
        await screenshot(page, "02_login_filled")
        await page.click('button[type="submit"]')
        # Wait for redirect after login — goes to /dashboard
        try:
            await page.wait_for_url("**/dashboard**", timeout=10000)
        except Exception:
            # Maybe slow redirect — wait a bit more
            await page.wait_for_timeout(3000)
        await screenshot(page, "03_signed_in")
        print(f"   After login URL: {page.url}")

        if "/auth/login" in page.url:
            print("   LOGIN FAILED — retrying...")
            await page.fill('#email', "test@example.com")
            await page.fill('#password', "password123")
            await page.click('button[type="submit"]')
            await page.wait_for_url("**/dashboard**", timeout=10000)
            print(f"   Retry URL: {page.url}")

        # ---- Step 2: Navigate to wizard ----
        print("2. Navigating to session wizard...")
        await page.goto(f"{BASE_URL}/session/new", wait_until="networkidle")
        await page.wait_for_timeout(2000)
        await screenshot(page, "04_wizard_step1")

        # ---- Step 3: Fill Step 1 — Job Search ----
        print("3. Filling job search fields...")
        await page.fill('#keywords', KEYWORDS)
        await page.wait_for_timeout(500)
        await page.fill('#locations', LOCATIONS)
        await page.wait_for_timeout(500)

        # Check the Remote Only checkbox
        remote_cb = page.locator('input[type="checkbox"]').first
        try:
            await remote_cb.check(timeout=3000)
        except Exception:
            print("   (no remote checkbox, skipping)")

        await screenshot(page, "05_step1_filled")

        # Click Next
        print("4. Clicking Next...")
        await page.click('button:has-text("Next")')
        await page.wait_for_timeout(2000)
        await screenshot(page, "06_step2_resume")

        # ---- Step 4: Fill Step 2 — Resume ----
        print("5. Filling resume...")
        await page.fill('#resumeText', RESUME_TEXT)
        await page.wait_for_timeout(500)
        await screenshot(page, "07_step2_filled")

        # Click Next
        print("6. Clicking Next to review...")
        await page.click('button:has-text("Next")')
        await page.wait_for_timeout(2000)
        await screenshot(page, "08_step3_review")

        # ---- Step 5: Launch ----
        print("7. Launching session...")
        await page.click('button:has-text("Start Job Hunt Session")')
        await page.wait_for_timeout(5000)
        session_url = page.url
        print(f"   Session URL: {session_url}")
        await screenshot(page, "09_session_launched")

        # ---- Step 6: Monitor pipeline ----
        print("8. Monitoring pipeline (up to 5 minutes)...")
        start_time = time.time()
        max_wait = 600  # 10 minutes — discovery with proxy is slow
        screenshot_count = 10

        while time.time() - start_time < max_wait:
            await page.wait_for_timeout(8000)

            screenshot_count += 1
            elapsed = int(time.time() - start_time)
            await screenshot(page, f"{screenshot_count:02d}_progress_{elapsed}s")

            # Read page text for status detection
            try:
                page_text = await page.inner_text("body")
            except Exception:
                continue

            # Check terminal states
            if "Session Summary" in page_text or "Session Complete" in page_text:
                print(f"   Session complete at {elapsed}s!")
                break
            # Only detect failure from the status badge, not sidebar counters
            if "Session Failed" in page_text:
                print(f"   Pipeline failed at {elapsed}s")
                break

            # HITL: Coach review gate
            approve_btn = page.locator('button:has-text("Approve & Start Job Discovery")')
            if await approve_btn.count() > 0:
                print(f"   Coach review gate at {elapsed}s — approving...")
                await screenshot(page, f"{screenshot_count:02d}_coach_review")
                await approve_btn.first.click()
                await page.wait_for_timeout(3000)
                screenshot_count += 1
                await screenshot(page, f"{screenshot_count:02d}_coach_approved")

            # HITL: Shortlist review gate — button text is "Apply to N Jobs"
            shortlist_btn = page.locator('button:has-text("Apply to")')
            if await shortlist_btn.count() > 0:
                btn_text = await shortlist_btn.first.inner_text()
                # Don't click if it says "Submitting..."
                if "Submitting" not in btn_text:
                    print(f"   Shortlist review gate at {elapsed}s — approving ({btn_text})...")
                    await screenshot(page, f"{screenshot_count:02d}_shortlist_review")
                    await shortlist_btn.first.click()
                    await page.wait_for_timeout(5000)
                    screenshot_count += 1
                    await screenshot(page, f"{screenshot_count:02d}_shortlist_approved")

            if elapsed % 30 < 10:
                print(f"   ... {elapsed}s elapsed ...")

        else:
            print(f"   Timed out after {max_wait}s")
            await screenshot(page, f"{screenshot_count + 1:02d}_timeout")

        # Final screenshot
        await screenshot(page, "99_final")

        print(f"\nDone! Total: {int(time.time() - start_time)}s")
        print(f"Screenshots in: {SCREENSHOTS_DIR}")

        await page.wait_for_timeout(3000)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
