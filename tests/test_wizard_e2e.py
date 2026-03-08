# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""End-to-end test: Drive the wizard UI → start session → monitor SSE → verify applications."""
import asyncio
import os
import json

async def main():
    from patchright.async_api import async_playwright

    screenshots_dir = "/Users/janedoe/Desktop/job-hunter-agent/screenshots"
    os.makedirs(screenshots_dir, exist_ok=True)
    resume_path = "/Users/janedoe/Desktop/Resumes/Jane_Doe_Resume_AI_Native_2026.pdf"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        page = await browser.new_page(viewport={"width": 1400, "height": 900})

        # Step 0: Log in
        print("Step 0: Logging in...")
        await page.goto("http://localhost:3000/auth/login", wait_until="networkidle", timeout=15000)
        await asyncio.sleep(1)

        email_input = await page.query_selector('input[name="email"]')
        pass_input = await page.query_selector('input[name="password"]')
        if email_input and pass_input:
            await email_input.fill("test@example.com")
            await pass_input.fill("testpass123")
            sign_in_btn = await page.query_selector('button[type="submit"]')
            if sign_in_btn:
                await sign_in_btn.click()
                await asyncio.sleep(3)
        print(f"  After login URL: {page.url}")
        await page.screenshot(path=f"{screenshots_dir}/wizard_00_login.png")

        # Step 1: Navigate to wizard
        print("\nStep 1: Loading wizard...")
        await page.goto("http://localhost:3000/session/new", wait_until="networkidle", timeout=15000)
        await asyncio.sleep(2)
        await page.screenshot(path=f"{screenshots_dir}/wizard_01_wizard.png")
        print(f"  URL: {page.url}")

        # Step 2: Fill Job Search form
        print("\nStep 2: Filling job search form...")

        # Keywords
        keywords_input = await page.query_selector('input[name="keywords"]')
        if keywords_input:
            await keywords_input.fill("AI Engineer, Machine Learning, Full Stack")
            print("  Filled keywords")

        # Locations
        locations_input = await page.query_selector('input[name="locations"]')
        if locations_input:
            await locations_input.fill("Remote, Austin TX")
            print("  Filled locations")

        # Remote only checkbox
        remote_checkbox = await page.query_selector('input[name="remoteOnly"]')
        if remote_checkbox:
            checked = await remote_checkbox.is_checked()
            if not checked:
                await remote_checkbox.check()
            print("  Checked remote only")

        # Salary
        salary_input = await page.query_selector('input[name="salaryMin"]')
        if salary_input:
            await salary_input.fill("150000")
            print("  Filled salary")

        await page.screenshot(path=f"{screenshots_dir}/wizard_03_step1_filled.png")

        # Click Next
        next_btn = await page.query_selector('button:has-text("Next")')
        if next_btn:
            await next_btn.click()
            await asyncio.sleep(1)
            print("  Clicked Next")

        await page.screenshot(path=f"{screenshots_dir}/wizard_04_step2.png")

        # Step 3: Upload resume
        print("\nStep 3: Uploading resume...")
        file_input = await page.query_selector('input[type="file"]')
        if file_input:
            await file_input.set_input_files(resume_path)
            print(f"  Uploaded: {resume_path}")
            await asyncio.sleep(3)  # Wait for parsing

        # LinkedIn URL (optional)
        linkedin_input = await page.query_selector('input[name="linkedinUrl"]')
        if linkedin_input:
            await linkedin_input.fill("https://www.linkedin.com/in/janedoe/")
            print("  Filled LinkedIn URL")

        await page.screenshot(path=f"{screenshots_dir}/wizard_05_step2_filled.png")

        # Click Next
        next_btn = await page.query_selector('button:has-text("Next")')
        if next_btn:
            await next_btn.click()
            await asyncio.sleep(1)
            print("  Clicked Next")

        await page.screenshot(path=f"{screenshots_dir}/wizard_06_step3_review.png")

        # Step 4: Review & Launch
        print("\nStep 4: Review page...")
        page_text = await page.evaluate("() => document.body.innerText.substring(0, 1000)")
        print(f"  Review content: {page_text[:300]}")

        # Click Launch
        launch_btn = None
        for selector in [
            'button:has-text("Launch")',
            'button:has-text("Start")',
            'button[type="submit"]',
        ]:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                launch_btn = el
                print(f"  Found launch button: {selector}")
                break

        if launch_btn:
            await launch_btn.click()
            print("  Clicked Launch!")
            await asyncio.sleep(3)

        await page.screenshot(path=f"{screenshots_dir}/wizard_07_session_start.png")
        print(f"  URL: {page.url}")

        # Step 5: Monitor session page
        if "/session/" in page.url:
            session_id = page.url.split("/session/")[1].split("?")[0].split("/")[0]
            print(f"\nSession started: {session_id}")

            # Monitor for 5 minutes max
            print("\nMonitoring session (5 min max)...")
            start_time = asyncio.get_event_loop().time()
            last_status = ""
            coach_review_done = False
            shortlist_review_done = False

            while asyncio.get_event_loop().time() - start_time < 300:
                await asyncio.sleep(5)
                elapsed = int(asyncio.get_event_loop().time() - start_time)

                # Check current status via API
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"http://localhost:8000/api/sessions/{session_id}") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            status = data.get("status", "unknown")
                            submitted = data.get("applications_submitted", 0)
                            failed = data.get("applications_failed", 0)

                            if status != last_status:
                                print(f"  [{elapsed}s] Status: {status} (submitted={submitted}, failed={failed})")
                                last_status = status
                                await page.screenshot(
                                    path=f"{screenshots_dir}/wizard_session_{status}_{elapsed}s.png"
                                )

                            # Handle coach review HITL
                            if status == "coaching" and not coach_review_done:
                                # Check if coach review modal is visible
                                modal = await page.query_selector('[data-testid="coach-review-modal"], .coach-review')
                                if not modal:
                                    # Check for any approval button
                                    approve_btn = await page.query_selector(
                                        'button:has-text("Approve"), button:has-text("Accept"), button:has-text("Continue")'
                                    )
                                    if approve_btn and await approve_btn.is_visible():
                                        print(f"  [{elapsed}s] Approving coach review...")
                                        await approve_btn.click()
                                        coach_review_done = True
                                        await asyncio.sleep(2)

                                # Also try API approval
                                if not coach_review_done:
                                    try:
                                        async with session.post(
                                            f"http://localhost:8000/api/sessions/{session_id}/coach-review",
                                            json={"approved": True}
                                        ) as resp2:
                                            if resp2.status in (200, 202):
                                                print(f"  [{elapsed}s] Coach review approved via API")
                                                coach_review_done = True
                                    except Exception:
                                        pass

                            # Handle shortlist review HITL
                            if status == "awaiting_review" and not shortlist_review_done:
                                # Get scored jobs and approve all
                                try:
                                    async with session.get(
                                        f"http://localhost:8000/api/sessions/{session_id}"
                                    ) as resp3:
                                        if resp3.status == 200:
                                            session_data = await resp3.json()
                                            # Try approving via UI first
                                            approve_btn = await page.query_selector(
                                                'button:has-text("Apply to All"), button:has-text("Approve"), button:has-text("Apply")'
                                            )
                                            if approve_btn and await approve_btn.is_visible():
                                                print(f"  [{elapsed}s] Approving shortlist via UI...")
                                                await approve_btn.click()
                                                shortlist_review_done = True
                                                await asyncio.sleep(2)
                                except Exception:
                                    pass

                                # Fallback: approve via API
                                if not shortlist_review_done:
                                    try:
                                        # Get job IDs from state
                                        async with session.get(
                                            f"http://localhost:8000/api/sessions/{session_id}/state"
                                        ) as resp4:
                                            state_data = await resp4.json() if resp4.status == 200 else {}
                                            scored_jobs = state_data.get("scored_jobs", [])
                                            job_ids = [j.get("job", {}).get("id", j.get("id", "")) for j in scored_jobs]
                                            if job_ids:
                                                async with session.post(
                                                    f"http://localhost:8000/api/sessions/{session_id}/review",
                                                    json={"approved_job_ids": job_ids}
                                                ) as resp5:
                                                    if resp5.status in (200, 202):
                                                        print(f"  [{elapsed}s] Shortlist approved via API ({len(job_ids)} jobs)")
                                                        shortlist_review_done = True
                                    except Exception as e:
                                        print(f"  [{elapsed}s] Shortlist approval error: {e}")

                            # Check if done
                            if status in ("completed", "failed", "paused"):
                                print(f"\n  Session ended: {status}")
                                print(f"  Submitted: {submitted}, Failed: {failed}")
                                break

                        else:
                            print(f"  [{elapsed}s] API returned {resp.status}")

            # Final screenshot
            await page.screenshot(path=f"{screenshots_dir}/wizard_08_final.png", full_page=True)
            print(f"\nFinal URL: {page.url}")

            # Get final session state
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:8000/api/sessions/{session_id}") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        print(f"\nFinal state:")
                        print(f"  Status: {data.get('status')}")
                        print(f"  Submitted: {data.get('applications_submitted')}")
                        print(f"  Failed: {data.get('applications_failed')}")
        else:
            print(f"\nDid not navigate to session page. URL: {page.url}")
            page_text = await page.evaluate("() => document.body.innerText.substring(0, 500)")
            print(f"  Page text: {page_text[:300]}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
