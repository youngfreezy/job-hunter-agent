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
KEYWORDS = "senior AI engineer, LLM engineer, agentic AI, full stack engineer"
LOCATIONS = "San Francisco, Remote"
RESUME_TEXT = """Jane Doe
Senior AI Engineer
San Francisco, CA 94105
(555) 123-4567
jane.doe@example.com

Senior AI Engineer with over ten years of software development experience across full-stack web applications, backend services, and AI-native systems. Builds production LLM platforms where models are first-class architecture components: agentic pipelines, HITL validation, and retrieval-augmented systems. Proven across React/Next.js, Python, Node.js, and AWS with a focus on evaluation-driven iteration and fast iteration cycles.

SKILLS
AI Systems & LLM Architecture: Agentic system design, orchestration, HITL validation, AI safety and guardrails, Prompt architecture, LLM evals, Evaluation-driven iteration, LangSmith, LangGraph, LangChain, LlamaIndex, Bedrock, AgentCore, OpenAI API
Vector Search & Retrieval: RAG, semantic retrieval, grounding, PGVector, vector embeddings
Backend: Node.js, NestJS, Express.js, Python, FastAPI, Flask, Ruby on Rails, Java
Cloud / DevOps: AWS (Lambda, S3, EC2, Step Functions), GCP (Vertex AI, Cloud Run), Azure ML, CI/CD: GitLab, GitHub Actions, CircleCI
Frontend: React, Next.js, TypeScript, JavaScript, Redux, HTML5, CSS3, Angular, D3.js
Databases: PostgreSQL, DynamoDB, MongoDB, Neo4j, PGVector, Redis
Testing & Quality: Jest, React Testing Library, Pytest, Playwright, Cypress, Storybook

AI-NATIVE SYSTEMS & AGENTIC APPLICATIONS
AEM Content Validator
- Designed LangGraph pipeline with 5 parallel agents and zero-cost triage router
- Reduced article validation from approx. 45 minutes to under 3 minutes
- Loaded 34 validation rules from Neo4j Aura graph DB with JSON fallback
- Grounded Accuracy Agent in PGVector; RAGAS evaluated faithfulness and recall
- LLM Judge synthesized approve/reject/needs-revision verdict
- Human reviewer gated via LangGraph interrupt() streamed to Next.js via SSE

AI Foundry Platform
- Shipped streaming chat on Bedrock/AgentCore with Vercel AI SDK and SSE
- Memory reconciliation eliminated CloudFront timeout errors across all deployments
- Built MCP server and model catalog for agent onboarding and spend tracking
- Designed three-agent Copilot system (Orchestrator, Planner, QA) with E2E tests

WORK HISTORY
Nov 2018 - Present: Sr Software Engineer, V2 Software LLC
- Mayo Clinic: Evolved AEM toward hybrid headless CMS; optimized GraphQL queries; built React component library; architected production LangGraph pipeline with 5 parallel agents
- Signet Jewelers: Built AI Foundry platform; authored custom Vercel AI SDK provider for Bedrock AgentCore with server-side streaming
- JP Morgan Chase: Developed React and Redux-based microfrontends; built backend services using Node.js and Express within AWS serverless architectures
- CACI (Army AI Maintenance, DoD): Led UI development for DoD secure apps; built ML output visualizations with Plotly.js. Active Secret Clearance.
- Rivian Automotive: Built React/Redux platform components; AWS Amplify backend with DynamoDB and Python Lambdas
- College Board: Architected React micro-frontend for Student Portal with Redux and AWS Serverless
- Etsy (Reverb): Led Plaid integration for secure financial account linking at scale
- Live Nation (Ticketmaster): Built front-end components using ReactJS, Redux, Next.js, and GraphQL
Jun 2017 - Nov 2018: Senior Software Engineer, CoStar Realty Group
Aug 2016 - Mar 2017: Sr Software Engineer, Datascan
Nov 2015 - Aug 2016: Software Engineer, General Electric

EDUCATION
MA: International Affairs and Economics, Columbia University, New York, NY
Professional Certificates: DeepLearning.AI & Udemy — Agentic AI Engineering Course, Data Analytics Foundations
"""


async def screenshot(page, name: str):
    path = SCREENSHOTS_DIR / f"{name}.png"
    await page.screenshot(path=str(path), full_page=True)
    print(f"  [screenshot] {path}")


async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=100)
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
        # Wait for redirect to session page (max 15s — backend API responds in ~36ms,
        # navigation should be fast with window.location.href)
        try:
            await page.wait_for_url("**/session/**", timeout=15000)
        except Exception:
            print(f"   WARNING: Still on {page.url} after 15s — checking...")
            await page.wait_for_timeout(3000)
        session_url = page.url
        print(f"   Session URL: {session_url}")
        await screenshot(page, "09_session_launched")

        # ---- Step 6: Monitor pipeline ----
        print("8. Monitoring pipeline (up to 20 minutes)...")
        start_time = time.time()
        max_wait = 1200  # 20 minutes — applying to 20+ jobs takes time
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
