# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Shared selector health-check runner.

Validates both discovery (board_selectors) and apply (apply_selectors) CSS
selectors against live pages. Used by both the API endpoint and the daily
scheduler.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Discovery health-check URLs (job search result pages)
_DISCOVERY_URLS = {
    "linkedin": "https://www.linkedin.com/jobs/search?keywords=software+engineer&f_WT=2",
    "indeed": "https://www.indeed.com/jobs?q=software+engineer",
    "glassdoor": "https://www.glassdoor.com/Job/software-engineer-jobs-SRCH_KO0,17.htm",
    "ziprecruiter": "https://www.ziprecruiter.com/jobs-search?search=software+engineer",
}

# Apply health-check URLs (job listing pages with apply buttons)
_APPLY_URLS = {
    "greenhouse": "https://boards.greenhouse.io/example",
    "lever": "https://jobs.lever.co/example",
    "linkedin": "https://www.linkedin.com/jobs/search/?keywords=software+engineer",
    "indeed": "https://www.indeed.com/jobs?q=software+engineer",
}


async def run_selector_health_check(platform: Optional[str] = None) -> Dict:
    """Validate all selectors against live pages. Returns results dict."""
    from backend.browser.manager import BrowserManager, apply_stealth
    from backend.shared.selector_memory import (
        get_all_for_board,
        record_health_check as record_discovery_health,
    )
    from backend.browser.tools.apply_selectors import (
        get_all_for_platform,
        record_health_check as record_apply_health,
    )

    results: Dict[str, Dict] = {"discovery": {}, "apply": {}}

    manager = BrowserManager()
    try:
        await manager.start(headless=True)

        # --- Discovery selectors (board_selectors) ---
        discovery_boards = [platform] if platform else list(_DISCOVERY_URLS.keys())
        for board in discovery_boards:
            url = _DISCOVERY_URLS.get(board)
            if not url:
                continue

            selectors = get_all_for_board(board)
            if not selectors:
                results["discovery"][board] = {"skipped": "No selectors stored"}
                continue

            ctx_id, context = await manager.new_context()
            page = await context.new_page()
            await apply_stealth(page)

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(2)

                board_results = []
                for sel_record in selectors:
                    sel = sel_record["selector"]
                    try:
                        elements = await page.query_selector_all(sel)
                        passed = len(elements) > 0
                    except Exception:
                        passed = False

                    record_discovery_health(board, sel, passed)
                    board_results.append({"selector": sel, "passed": passed})

                results["discovery"][board] = {
                    "checked": len(board_results),
                    "passed": sum(1 for r in board_results if r["passed"]),
                    "details": board_results,
                }
            except Exception as exc:
                results["discovery"][board] = {"error": str(exc)}
            finally:
                await manager.close_context(ctx_id)

        # --- Apply selectors (apply_selectors) ---
        apply_platforms = [platform] if platform else list(_APPLY_URLS.keys())
        for plat in apply_platforms:
            url = _APPLY_URLS.get(plat)
            if not url:
                continue

            selectors = get_all_for_platform(plat)
            if not selectors:
                results["apply"][plat] = {"skipped": "No selectors stored"}
                continue

            ctx_id, context = await manager.new_context()
            page = await context.new_page()
            await apply_stealth(page)

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(2)

                plat_results = []
                for sel_record in selectors:
                    sel = sel_record["selector"]
                    step_type = sel_record["step_type"]
                    try:
                        el = await page.query_selector(sel)
                        passed = el is not None
                    except Exception:
                        passed = False

                    record_apply_health(plat, step_type, sel, passed)
                    plat_results.append({
                        "selector": sel,
                        "step_type": step_type,
                        "passed": passed,
                    })

                results["apply"][plat] = {
                    "checked": len(plat_results),
                    "passed": sum(1 for r in plat_results if r["passed"]),
                    "details": plat_results,
                }
            except Exception as exc:
                results["apply"][plat] = {"error": str(exc)}
            finally:
                await manager.close_context(ctx_id)

    except Exception as exc:
        logger.exception("Selector health-check failed")
        return {"error": str(exc)}
    finally:
        await manager.stop()

    # Log summary
    for category in ("discovery", "apply"):
        for plat, data in results[category].items():
            if "checked" in data:
                logger.info(
                    "Health-check %s/%s: %d/%d passed",
                    category, plat, data["passed"], data["checked"],
                )

    return results
