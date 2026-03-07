"""Pilot -- the main LLM-steered browser automation interface.

Wraps BrowserManager + form_filler into a single high-level API that can be
used independently of the JobHunter application layer.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.browser.manager import BrowserManager
from backend.browser.tools.form_filler import (
    analyse_form,
    extract_form_fields,
    fill_form,
)

logger = logging.getLogger(__name__)


class Pilot:
    """High-level LLM-steered browser automation.

    Manages browser lifecycle and provides simple methods for:
    - Navigating to pages
    - Extracting form fields from any page
    - Using an LLM to determine fill values
    - Filling forms automatically
    - Detecting page states (confirmation, login, verification)

    Can be used as an async context manager::

        async with Pilot(mode="cdp") as pilot:
            page = await pilot.new_page()
            await pilot.navigate(page, url)
            result = await pilot.auto_fill(page, user_data, resume_text)
    """

    def __init__(
        self,
        mode: str = "patchright",
        headless: bool = True,
    ) -> None:
        self._manager = BrowserManager()
        self._mode = mode
        self._headless = headless
        self._ctx_id: Optional[str] = None

    async def __aenter__(self) -> "Pilot":
        await self.start()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.stop()

    async def start(self) -> None:
        """Start the browser engine."""
        if self._mode == "brightdata":
            await self._manager.start_brightdata()
        elif self._mode == "cdp":
            await self._manager.start_cdp(headless=self._headless)
        else:
            await self._manager.start(headless=self._headless)

    async def stop(self) -> None:
        """Stop the browser and clean up."""
        await self._manager.stop()

    async def new_page(self, proxy: Optional[str] = None) -> Any:
        """Create a new stealth page ready for automation.

        Returns a Playwright Page with anti-detection applied.
        """
        ctx_id, page = await self._manager.new_stealth_page(
            context_id=self._ctx_id, proxy=proxy
        )
        self._ctx_id = ctx_id
        return page

    async def navigate(self, page: Any, url: str, wait_until: str = "domcontentloaded") -> None:
        """Navigate to a URL and wait for the page to load."""
        await page.goto(url, wait_until=wait_until, timeout=30000)

    async def extract_fields(self, page: Any) -> List[Dict[str, Any]]:
        """Extract all visible form fields from the current page.

        Returns a list of field descriptors with selector, type, label, options.
        """
        return await extract_form_fields(page)

    async def analyse_fields(
        self,
        fields: List[Dict[str, Any]],
        resume_text: str,
        cover_letter: str = "",
        job_title: str = "",
        job_company: str = "",
        user_profile: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """Use an LLM to determine the best fill value for each field.

        Returns a list of fill instructions (selector, action, value).
        """
        return await analyse_form(
            fields=fields,
            resume_text=resume_text,
            cover_letter=cover_letter,
            job_title=job_title,
            job_company=job_company,
            user_profile=user_profile,
        )

    async def fill(
        self,
        page: Any,
        instructions: List[Dict[str, Any]],
        resume_file_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute fill instructions on the page.

        Returns summary dict with filled, skipped, errors counts.
        """
        return await fill_form(
            page=page,
            instructions=instructions,
            resume_file_path=resume_file_path,
        )

    async def auto_fill(
        self,
        page: Any,
        resume_text: str,
        cover_letter: str = "",
        job_title: str = "",
        job_company: str = "",
        resume_file_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """One-shot: extract fields, analyse with LLM, and fill the form.

        Convenience method that chains extract_fields → analyse_fields → fill.
        """
        fields = await self.extract_fields(page)
        if not fields:
            return {"filled": 0, "skipped": 0, "errors": ["No form fields found"]}

        instructions = await self.analyse_fields(
            fields=fields,
            resume_text=resume_text,
            cover_letter=cover_letter,
            job_title=job_title,
            job_company=job_company,
        )

        return await self.fill(
            page=page,
            instructions=instructions,
            resume_file_path=resume_file_path,
        )

    @property
    def is_running(self) -> bool:
        return self._manager.is_running

    @property
    def mode(self) -> str:
        return self._manager.mode
