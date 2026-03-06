"""Selector health-check API -- validates stored CSS selectors against live pages."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter

from backend.browser.tools.apply_selectors import (
    get_all_for_platform,
    get_all_selectors,
    record_health_check,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/selectors", tags=["selectors"])

# Sample pages to test selectors against (one per platform)
_HEALTH_CHECK_URLS = {
    "linkedin": "https://www.linkedin.com/jobs/search/?keywords=software+engineer",
    "indeed": "https://www.indeed.com/jobs?q=software+engineer",
    "glassdoor": "https://www.glassdoor.com/Job/software-engineer-jobs-SRCH_KO0,17.htm",
    "ziprecruiter": "https://www.ziprecruiter.com/jobs-search?search=software+engineer",
    "greenhouse": "https://boards.greenhouse.io/example",
    "lever": "https://jobs.lever.co/example",
    "workday": "https://example.wd5.myworkdayjobs.com/en-US/External",
}


@router.get("/status")
async def selector_status(platform: Optional[str] = None):
    """Return current selector health for all or a specific platform."""
    if platform:
        selectors = get_all_for_platform(platform)
    else:
        selectors = get_all_selectors()

    return {"selectors": selectors, "count": len(selectors)}


@router.post("/health-check")
async def trigger_health_check(platform: Optional[str] = None):
    """Run selector validation against live pages.

    Navigates to a sample page for each platform and checks if stored
    selectors still find elements. Records pass/fail per selector.
    """
    from backend.browser.manager import BrowserManager, apply_stealth

    platforms = [platform] if platform else list(_HEALTH_CHECK_URLS.keys())
    results = {}

    manager = BrowserManager()
    try:
        await manager.start(headless=True)

        for plat in platforms:
            url = _HEALTH_CHECK_URLS.get(plat)
            if not url:
                results[plat] = {"error": f"No health-check URL for {plat}"}
                continue

            selectors = get_all_for_platform(plat)
            if not selectors:
                results[plat] = {"skipped": "No selectors stored"}
                continue

            ctx_id, context = await manager.new_context()
            page = await context.new_page()
            await apply_stealth(page)

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                import asyncio
                await asyncio.sleep(2)  # settle

                plat_results = []
                for sel_record in selectors:
                    sel = sel_record["selector"]
                    step_type = sel_record["step_type"]
                    try:
                        el = await page.query_selector(sel)
                        passed = el is not None
                    except Exception:
                        passed = False

                    record_health_check(plat, step_type, sel, passed)
                    plat_results.append({
                        "selector": sel,
                        "step_type": step_type,
                        "passed": passed,
                    })

                results[plat] = {
                    "checked": len(plat_results),
                    "passed": sum(1 for r in plat_results if r["passed"]),
                    "details": plat_results,
                }
            except Exception as exc:
                results[plat] = {"error": str(exc)}
            finally:
                await manager.close_context(ctx_id)

    except Exception as exc:
        return {"error": str(exc)}
    finally:
        await manager.stop()

    return {"results": results}
