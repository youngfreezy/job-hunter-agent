# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Base scraper class with shared utilities for all job board scrapers.

Every job board scraper inherits from :class:`BaseScraper` to get consistent
rate-limiting, scrolling, text extraction, and captcha-detection behaviour.
"""

from __future__ import annotations

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from typing import Any, List, Optional

from backend.browser.anti_detect.stealth import apply_stealth
from backend.browser.manager import BrowserManager
from backend.shared.models.schemas import JobListing

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Abstract base class for job board scrapers.

    Subclasses must implement :meth:`scrape` and can leverage the helper
    methods defined here for common browser automation patterns.
    """

    # Human-readable name (override in subclasses)
    BOARD_NAME: str = "base"

    def __init__(self, browser_manager: Optional[BrowserManager] = None) -> None:
        self._manager = browser_manager
        self._owns_manager = browser_manager is None

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def scrape(
        self,
        keywords: list[str],
        locations: list[str],
        remote_only: bool = False,
        max_results: int = 50,
    ) -> list[JobListing]:
        """Scrape job listings matching the given criteria.

        Must return a (possibly partial) list of :class:`JobListing` models.
        """
        ...

    # ------------------------------------------------------------------
    # Browser manager helpers
    # ------------------------------------------------------------------

    async def _ensure_manager(self) -> BrowserManager:
        """Return a running BrowserManager, creating one if necessary."""
        if self._manager is None:
            self._manager = BrowserManager()
            self._owns_manager = True

        if not self._manager.is_running:
            await self._manager.start_for_task(board=self.BOARD_NAME, purpose="discovery")

        return self._manager

    async def _cleanup_manager(self) -> None:
        """Stop the browser manager if we own it."""
        if self._owns_manager and self._manager and self._manager.is_running:
            await self._manager.stop()

    # ------------------------------------------------------------------
    # Rate-limiting / timing
    # ------------------------------------------------------------------

    @staticmethod
    async def _random_delay(min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
        """Sleep for a random duration to mimic human pacing.

        Parameters
        ----------
        min_seconds:
            Minimum delay in seconds (inclusive).
        max_seconds:
            Maximum delay in seconds (inclusive).
        """
        delay = random.uniform(min_seconds, max_seconds)
        logger.debug("Sleeping %.2fs for rate-limiting", delay)
        await asyncio.sleep(delay)

    @staticmethod
    async def _short_delay() -> None:
        """Very brief pause (0.3-0.8s) between rapid UI interactions."""
        await asyncio.sleep(random.uniform(0.3, 0.8))

    # ------------------------------------------------------------------
    # Page interaction helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _scroll_page(
        page: Any,
        scroll_count: int = 3,
        delay_between: float = 1.0,
    ) -> None:
        """Scroll the page down incrementally to trigger lazy-loading.

        Parameters
        ----------
        page:
            Playwright ``Page`` object.
        scroll_count:
            Number of scroll-down actions to perform.
        delay_between:
            Seconds to wait between each scroll (allows content to load).
        """
        for i in range(scroll_count):
            # Scroll by a random amount near one viewport height
            scroll_px = random.randint(600, 900)
            await page.evaluate(f"window.scrollBy(0, {scroll_px})")
            await asyncio.sleep(delay_between + random.uniform(0, 0.5))
            logger.debug("Scroll %d/%d (%dpx)", i + 1, scroll_count, scroll_px)

    @staticmethod
    async def _scroll_to_bottom(page: Any, max_scrolls: int = 10) -> None:
        """Repeatedly scroll to the bottom until no new content loads.

        Useful for infinite-scroll pages like LinkedIn.
        """
        previous_height = 0
        for i in range(max_scrolls):
            current_height = await page.evaluate("document.body.scrollHeight")
            if current_height == previous_height:
                logger.debug("Reached bottom of page after %d scrolls", i)
                break
            previous_height = current_height
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(random.uniform(1.5, 2.5))

    @staticmethod
    async def _extract_text(page: Any, selector: str, default: str = "") -> str:
        """Safely extract text content from a CSS selector.

        Returns *default* if the element is missing or extraction fails.
        """
        try:
            element = await page.query_selector(selector)
            if element:
                text = await element.text_content()
                return (text or "").strip()
        except Exception:
            pass
        return default

    @staticmethod
    async def _extract_attribute(
        page: Any,
        selector: str,
        attribute: str,
        default: str = "",
    ) -> str:
        """Safely extract an attribute value from a CSS selector."""
        try:
            element = await page.query_selector(selector)
            if element:
                value = await element.get_attribute(attribute)
                return (value or "").strip()
        except Exception:
            pass
        return default

    @staticmethod
    async def _extract_text_from_element(element: Any, selector: str, default: str = "") -> str:
        """Extract text from a child element within a parent element handle."""
        try:
            child = await element.query_selector(selector)
            if child:
                text = await child.text_content()
                return (text or "").strip()
        except Exception:
            pass
        return default

    @staticmethod
    async def _extract_attr_from_element(
        element: Any,
        selector: str,
        attribute: str,
        default: str = "",
    ) -> str:
        """Extract an attribute from a child element within a parent element handle."""
        try:
            child = await element.query_selector(selector)
            if child:
                value = await child.get_attribute(attribute)
                return (value or "").strip()
        except Exception:
            pass
        return default

    # ------------------------------------------------------------------
    # Captcha / block detection
    # ------------------------------------------------------------------

    @staticmethod
    async def _handle_captcha(page: Any) -> bool:
        """Detect and attempt basic handling of captcha / block pages.

        Returns ``True`` if a captcha/block was detected (the caller should
        back off or return partial results).

        NOTE: Full captcha solving is out of scope.  This method only
        detects common block pages so scrapers can abort gracefully.
        """
        # Common block / captcha indicators
        block_selectors = [
            "#captcha-form",
            ".captcha-container",
            "[data-captcha]",
            "#px-captcha",           # PerimeterX
            ".cf-challenge-running",  # Cloudflare challenge
            "#challenge-running",
            "#recaptcha",
            ".g-recaptcha",
            "#challenge-form",
        ]

        for selector in block_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    logger.warning(
                        "Captcha / block detected on %s (matched: %s)",
                        page.url,
                        selector,
                    )
                    return True
            except Exception:
                continue

        # Also check page title for common block messages
        try:
            title = await page.title()
            block_phrases = [
                "access denied",
                "blocked",
                "captcha",
                "are you a robot",
                "verify you are human",
                "security check",
                "just a moment",  # Cloudflare
            ]
            title_lower = (title or "").lower()
            for phrase in block_phrases:
                if phrase in title_lower:
                    logger.warning("Block detected via page title: '%s'", title)
                    return True
        except Exception:
            pass

        return False

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------

    def _log_scrape_start(
        self,
        keywords: list[str],
        locations: list[str],
        max_results: int,
    ) -> None:
        logger.info(
            "[%s] Starting scrape -- keywords=%s, locations=%s, max=%d",
            self.BOARD_NAME,
            keywords,
            locations,
            max_results,
        )

    def _log_scrape_end(self, count: int) -> None:
        logger.info("[%s] Scrape complete -- %d listings collected", self.BOARD_NAME, count)

    def _log_page(self, page_num: int, url: str) -> None:
        logger.debug("[%s] Fetching page %d: %s", self.BOARD_NAME, page_num, url)
