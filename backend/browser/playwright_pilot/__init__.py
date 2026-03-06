"""playwright-pilot: LLM-steered browser automation built on Playwright.

A thin abstraction layer that combines:
- Browser lifecycle management (Playwright/Patchright, CDP)
- LLM-driven form analysis and filling (via Claude)
- Anti-detection and stealth configuration
- Page interaction utilities (click, wait, detect)

Designed to be extractable as a standalone open-source package.

Usage::

    from backend.browser.playwright_pilot import Pilot

    async with Pilot() as pilot:
        page = await pilot.new_page()
        await pilot.navigate(page, "https://example.com/apply")
        fields = await pilot.extract_fields(page)
        await pilot.fill_form(page, fields, user_data={...})
"""

from backend.browser.playwright_pilot.pilot import Pilot

__all__ = ["Pilot"]
