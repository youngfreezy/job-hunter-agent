# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Isolated test: Apply to a single job URL with live screenshot streaming.

Runs the same steps as the application agent but with verbose logging
and a simple HTTP server that streams screenshots to a browser tab.

Usage:
    python test_apply_isolated.py <JOB_URL>
    # Open http://localhost:9222 to see live screenshots
"""

import asyncio
import base64
import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("test_apply")

# Suppress noisy loggers
for name in ("urllib3", "httpcore", "httpx", "asyncio"):
    logging.getLogger(name).setLevel(logging.WARNING)

SCREENSHOTS_DIR = Path(__file__).parent / "test_apply_screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)

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

# Global state for the screenshot server
_latest_screenshot: Optional[str] = None
_latest_status: str = "Starting..."
_log_lines: list = []


def _log(msg: str):
    """Log and store for the viewer."""
    logger.info(msg)
    _log_lines.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
    if len(_log_lines) > 200:
        _log_lines.pop(0)


async def save_screenshot(page, name: str):
    """Save screenshot to disk and update global for streaming."""
    global _latest_screenshot
    path = SCREENSHOTS_DIR / f"{name}.png"
    await page.screenshot(path=str(path), full_page=False)
    # Also store as base64 for the live viewer
    with open(path, "rb") as f:
        _latest_screenshot = base64.b64encode(f.read()).decode("utf-8")
    _log(f"Screenshot: {name}")


async def screenshot_loop(page):
    """Background task: capture screenshots every 1.5s for the live viewer."""
    global _latest_screenshot
    while True:
        try:
            screenshot_bytes = await page.screenshot(type="jpeg", quality=50, full_page=False)
            _latest_screenshot = base64.b64encode(screenshot_bytes).decode("utf-8")
        except Exception:
            pass
        await asyncio.sleep(1.5)


# ---------------------------------------------------------------------------
# Simple HTTP server for live screenshot viewer
# ---------------------------------------------------------------------------

VIEWER_HTML = """<!DOCTYPE html>
<html><head><title>Apply Test - Live View</title>
<style>
body { margin: 0; font-family: monospace; background: #111; color: #eee; display: flex; height: 100vh; }
#screenshot { flex: 2; display: flex; align-items: center; justify-content: center; background: #000; }
#screenshot img { max-width: 100%; max-height: 100%; object-fit: contain; }
#sidebar { flex: 1; max-width: 400px; padding: 12px; overflow-y: auto; font-size: 12px; border-left: 1px solid #333; }
#status { color: #0f0; font-size: 14px; margin-bottom: 8px; }
#log { white-space: pre-wrap; color: #aaa; }
</style></head>
<body>
<div id="screenshot"><img id="img" src="" alt="Waiting for screenshot..."></div>
<div id="sidebar">
  <div id="status">Connecting...</div>
  <div id="log"></div>
</div>
<script>
async function poll() {
  try {
    const r = await fetch('/state');
    const d = await r.json();
    if (d.screenshot) document.getElementById('img').src = 'data:image/jpeg;base64,' + d.screenshot;
    document.getElementById('status').textContent = d.status;
    document.getElementById('log').textContent = d.logs.join('\\n');
    // Auto-scroll
    const sidebar = document.getElementById('sidebar');
    sidebar.scrollTop = sidebar.scrollHeight;
  } catch(e) {}
  setTimeout(poll, 1000);
}
poll();
</script>
</body></html>"""


async def handle_http(reader, writer):
    """Minimal HTTP handler for the live viewer."""
    data = await reader.read(4096)
    request_line = data.decode().split("\r\n")[0]
    path = request_line.split(" ")[1] if " " in request_line else "/"

    if path == "/state":
        body = json.dumps({
            "screenshot": _latest_screenshot,
            "status": _latest_status,
            "logs": _log_lines[-80:],
        })
        response = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            f"Content-Length: {len(body)}\r\n"
            "\r\n" + body
        )
    else:
        body = VIEWER_HTML
        response = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/html\r\n"
            f"Content-Length: {len(body)}\r\n"
            "\r\n" + body
        )

    writer.write(response.encode())
    await writer.drain()
    writer.close()


async def start_viewer_server():
    """Start a tiny HTTP server on port 9222 for the live screenshot viewer."""
    server = await asyncio.start_server(handle_http, "127.0.0.1", 9222)
    _log("Live viewer at http://localhost:9222")
    return server


# ---------------------------------------------------------------------------
# Main test flow
# ---------------------------------------------------------------------------

async def test_apply(job_url: str):
    """Test applying to a single job URL step by step with live screenshots."""
    global _latest_status

    # Apply patches first
    from backend.shared import patches
    patches.apply_all()

    from backend.browser.manager import BrowserManager
    from backend.browser.anti_detect.stealth import apply_stealth
    from backend.browser.tools.ats_detector import detect_ats_type
    from backend.browser.tools.form_filler import extract_form_fields, analyse_form, fill_form
    from backend.browser.tools.cover_letter import generate_cover_letter
    from backend.browser.tools.account_creator import detect_account_required
    from backend.shared.models.schemas import JobListing, JobBoard

    manager = BrowserManager()
    ctx_id = None
    screenshot_task = None

    try:
        _latest_status = "Launching browser..."
        _log(f"=== Isolated Application Test ===")
        _log(f"Job URL: {job_url}")

        # Step 1: Launch browser
        _log("Step 1: Starting browser...")
        await manager.start()
        ctx_id, context = await manager.new_context()
        page = await context.new_page()
        await apply_stealth(page)
        _log("Browser ready")

        # Start background screenshot streaming
        screenshot_task = asyncio.create_task(screenshot_loop(page))

        # Step 2: Navigate
        _latest_status = "Navigating to job page..."
        _log(f"Step 2: Navigating to {job_url}")
        try:
            await page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
        except Exception as e:
            _log(f"ERROR: Navigation failed: {e}")
            await save_screenshot(page, "01_navigation_failed")
            return

        await save_screenshot(page, "01_page_loaded")
        title = await page.title()
        _log(f"Page title: {title}")
        _log(f"Page URL: {page.url}")

        # Check if we got a real job page
        if "Not Found" in title or "404" in title or "Error" in title:
            _log("WARNING: Page appears to be an error page")

        # Step 3: Detect ATS
        _latest_status = "Detecting ATS type..."
        _log("Step 3: Detecting ATS type...")
        ats_type = None
        try:
            ats_type = await detect_ats_type(page)
            _log(f"ATS detected: {ats_type.value}")
        except Exception as e:
            _log(f"ERROR: ATS detection failed: {e}")

        await save_screenshot(page, "02_ats_detected")

        # Step 4: Check account required
        _latest_status = "Checking account requirements..."
        _log("Step 4: Checking if account creation needed...")
        try:
            needs_account = await detect_account_required(page)
            _log(f"Account needed: {needs_account}")
        except Exception as e:
            _log(f"ERROR: Account check failed: {e}")
            needs_account = False

        # Step 5: Look for Apply button / link
        _latest_status = "Looking for Apply button..."
        _log("Step 5: Looking for Apply button or link...")
        apply_selectors = [
            'button:has-text("Apply")',
            'a:has-text("Apply")',
            'button:has-text("Apply now")',
            'a:has-text("Apply now")',
            '#applyButtonLinkContainer a',
            '.jobsearch-IndeedApplyButton',
            'button[data-testid="apply-button"]',
        ]
        apply_btn = None
        for sel in apply_selectors:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    txt = await el.inner_text()
                    _log(f"  Found apply element: '{txt}' ({sel})")
                    apply_btn = el
                    break
            except Exception:
                pass

        if apply_btn:
            _log("Clicking apply button...")
            try:
                await apply_btn.click()
                await page.wait_for_timeout(3000)
                await save_screenshot(page, "03_after_apply_click")
                _log(f"After click URL: {page.url}")
            except Exception as e:
                _log(f"ERROR: Apply click failed: {e}")
        else:
            _log("No apply button found — may already be on application form")

        # Step 6: Extract form fields
        _latest_status = "Extracting form fields..."
        _log("Step 6: Extracting form fields...")
        form_fields = None
        try:
            form_fields = await extract_form_fields(page)
            count = len(form_fields) if form_fields else 0
            _log(f"Found {count} form fields")
            if form_fields:
                for i, field in enumerate(form_fields[:15]):
                    _log(f"  Field {i}: {field}")
        except Exception as e:
            _log(f"ERROR: Form field extraction failed: {e}")

        await save_screenshot(page, "04_form_extracted")

        # Step 7: Generate cover letter
        _latest_status = "Generating cover letter..."
        _log("Step 7: Generating cover letter...")
        dummy_job = JobListing(
            id="test-001",
            title=title or "Software Engineer",
            company="Unknown",
            location="Remote",
            url=job_url,
            board=JobBoard.INDEED,
            ats_type=ats_type.value if ats_type else "unknown",
        )
        cover_letter = None
        try:
            cover_letter = await generate_cover_letter(
                job=dummy_job,
                resume_text=RESUME_TEXT,
                template="",
            )
            _log(f"Cover letter generated ({len(cover_letter.text)} chars)")
            _log(f"  Preview: {cover_letter.text[:150]}...")
        except Exception as e:
            _log(f"ERROR: Cover letter generation failed: {e}")

        # Step 8: Analyse and fill form
        if form_fields:
            _latest_status = "Analysing form..."
            _log("Step 8: Analysing form fields with Claude...")
            fill_instructions = None
            try:
                fill_instructions = await analyse_form(
                    fields=form_fields,
                    resume_text=RESUME_TEXT,
                    cover_letter=cover_letter.text if cover_letter else "",
                    job_title=dummy_job.title,
                    job_company=dummy_job.company,
                    ats_strategy=None,
                )
                count = len(fill_instructions) if fill_instructions else 0
                _log(f"Fill instructions generated: {count} actions")
                if fill_instructions:
                    for i, instr in enumerate(fill_instructions[:10]):
                        _log(f"  Instruction {i}: {instr}")
            except Exception as e:
                _log(f"ERROR: Form analysis failed: {e}")

            if fill_instructions:
                _latest_status = "Filling form..."
                _log("Step 8b: Filling form...")
                try:
                    fill_result = await fill_form(page, fill_instructions, resume_file_path=None)
                    _log(f"Fill result: filled={fill_result.get('filled', 0)}, "
                         f"skipped={fill_result.get('skipped', 0)}, "
                         f"errors={fill_result.get('errors', [])}")
                except Exception as e:
                    _log(f"ERROR: Form filling failed: {e}")

            await save_screenshot(page, "05_form_filled")
        else:
            _log("No form fields found — skipping fill steps")

        # Step 9: Look for submit button (dry run)
        _latest_status = "Looking for submit button..."
        _log("Step 9: Looking for submit button...")
        submit_btn = await page.query_selector(
            'button[type="submit"], '
            'button:has-text("Submit"), '
            'button:has-text("Apply"), '
            'button:has-text("Submit Application"), '
            'input[type="submit"]'
        )
        if submit_btn:
            try:
                btn_text = await submit_btn.inner_text()
            except Exception:
                btn_text = "(input element)"
            _log(f"Submit button found: '{btn_text}'")
            _log("DRY RUN — not clicking submit")
        else:
            _log("No submit button found on page")

        await save_screenshot(page, "06_final")
        _latest_status = "Test complete!"
        _log("=== Test complete ===")

        # Keep viewer alive for a bit so user can review
        _log("Keeping browser open for 30s so you can review...")
        await asyncio.sleep(30)

    except Exception as exc:
        _latest_status = f"ERROR: {exc}"
        _log(f"Test failed with error: {exc}")
        import traceback
        _log(traceback.format_exc())
        try:
            await save_screenshot(page, "99_error")
        except Exception:
            pass
    finally:
        if screenshot_task:
            screenshot_task.cancel()
            try:
                await screenshot_task
            except asyncio.CancelledError:
                pass
        if ctx_id:
            await manager.close_context(ctx_id)
        await manager.stop()


async def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.indeed.com/viewjob?jk=abc123"

    # Start the live viewer server
    server = await start_viewer_server()

    try:
        await test_apply(url)
    finally:
        server.close()
        await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
