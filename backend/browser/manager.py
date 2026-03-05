"""Browser lifecycle manager for the JobHunter Agent.

Manages Playwright browser instances using Patchright (a patched build of
Playwright with built-in anti-detection).  Each user session gets an isolated
BrowserContext with randomised fingerprints and optional proxy support.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import uuid4

from patchright.async_api import async_playwright, Browser, BrowserContext, Playwright

from backend.browser.anti_detect.stealth import (
    apply_stealth,
    get_random_locale_timezone,
    get_random_user_agent,
    get_random_viewport,
    get_stealth_config,
)
from backend.shared.config import settings

logger = logging.getLogger(__name__)


class BrowserManager:
    """Manages a single Chromium browser process and multiple isolated contexts.

    Usage::

        mgr = BrowserManager()
        await mgr.start()

        ctx_id, context = await mgr.new_context(proxy="http://user:pass@host:port")
        page = await context.new_page()
        ...
        await mgr.close_context(ctx_id)

        await mgr.stop()
    """

    def __init__(self) -> None:
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._contexts: Dict[str, BrowserContext] = {}
        self._running: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Launch the Playwright runtime and browser process.

        Uses Patchright's Chromium build which includes anti-detection
        patches at the browser level.
        """
        if self._running:
            logger.warning("BrowserManager.start() called but already running")
            return

        logger.info("Starting Patchright browser engine")
        self._playwright = await async_playwright().start()

        stealth_cfg = get_stealth_config()

        self._browser = await self._playwright.chromium.launch(
            headless=stealth_cfg["headless"],
            args=stealth_cfg["args"],
            ignore_default_args=stealth_cfg["ignore_default_args"],
        )
        self._running = True
        logger.info("Browser engine started (pid=%s)", self._browser.contexts)

    async def stop(self) -> None:
        """Gracefully shut down all contexts and the browser process."""
        if not self._running:
            return

        logger.info("Stopping BrowserManager -- closing %d contexts", len(self._contexts))

        # Close all open contexts first
        for ctx_id in list(self._contexts):
            await self.close_context(ctx_id)

        if self._browser:
            await self._browser.close()
            self._browser = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

        self._running = False
        logger.info("BrowserManager stopped")

    # ------------------------------------------------------------------
    # Context management
    # ------------------------------------------------------------------

    async def new_context(
        self,
        proxy: Optional[str] = None,
    ) -> tuple[str, BrowserContext]:
        """Create a new isolated BrowserContext with anti-detection settings.

        Parameters
        ----------
        proxy:
            Optional proxy URL (``http://user:pass@host:port``).  Falls back
            to ``settings.PROXY_URL`` if not provided and the env var is set.

        Returns
        -------
        tuple[str, BrowserContext]
            A ``(context_id, context)`` pair.  Use the *context_id* later to
            close the context via :meth:`close_context`.
        """
        if not self._running or self._browser is None:
            raise RuntimeError("BrowserManager is not running. Call start() first.")

        ctx_id = uuid4().hex[:12]

        # Randomise fingerprint
        user_agent = get_random_user_agent()
        viewport = get_random_viewport()
        locale, timezone_id = get_random_locale_timezone()

        # Build context options
        ctx_options: Dict[str, Any] = {
            "user_agent": user_agent,
            "viewport": viewport,
            "locale": locale,
            "timezone_id": timezone_id,
            "color_scheme": "light",
            "java_script_enabled": True,
            "bypass_csp": True,
            "ignore_https_errors": True,
            # Realistic accept-language header
            "extra_http_headers": {
                "Accept-Language": f"{locale},{locale.split('-')[0]};q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            },
            # Geolocation permission for sites that check
            "permissions": ["geolocation"],
        }

        # Proxy: explicit arg > settings.PROXY_URL > none
        effective_proxy = proxy or settings.PROXY_URL
        if effective_proxy:
            ctx_options["proxy"] = {"server": effective_proxy}
            logger.debug("Context %s using proxy %s", ctx_id, effective_proxy)

        context = await self._browser.new_context(**ctx_options)
        # Note: stealth JS is applied per-page via apply_stealth() in each
        # scraper.  Do NOT use context.add_init_script here — it causes
        # ERR_NAME_NOT_RESOLVED with patchright.

        self._contexts[ctx_id] = context
        logger.info(
            "Created browser context %s (viewport=%sx%s, locale=%s, tz=%s)",
            ctx_id,
            viewport["width"],
            viewport["height"],
            locale,
            timezone_id,
        )
        return ctx_id, context

    async def close_context(self, context_id: str) -> None:
        """Close and remove the context identified by *context_id*.

        Silently does nothing if the context has already been closed or does
        not exist.
        """
        context = self._contexts.pop(context_id, None)
        if context is None:
            logger.debug("Context %s not found (already closed?)", context_id)
            return

        try:
            await context.close()
            logger.info("Closed browser context %s", context_id)
        except Exception:
            logger.warning("Error closing context %s (may already be closed)", context_id, exc_info=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def new_stealth_page(
        self,
        context_id: Optional[str] = None,
        proxy: Optional[str] = None,
    ) -> tuple[str, Any]:
        """Convenience: create a context (if needed) and return a stealth page.

        Returns
        -------
        tuple[str, Page]
            ``(context_id, page)`` -- the page already has stealth JS applied.
        """
        if context_id and context_id in self._contexts:
            context = self._contexts[context_id]
        else:
            context_id, context = await self.new_context(proxy=proxy)

        page = await context.new_page()
        await apply_stealth(page)
        return context_id, page

    @property
    def is_running(self) -> bool:
        """Return ``True`` if the browser process is alive."""
        return self._running

    @property
    def open_contexts(self) -> int:
        """Return the number of open browser contexts."""
        return len(self._contexts)
