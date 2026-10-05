# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Browser lifecycle manager for the JobHunter Agent.

Manages Playwright browser instances using either:
1. Patchright (patched Chromium with anti-detection) — default for discovery
2. Real Chrome via CDP — for applications (bypasses reCAPTCHA Enterprise)

Each user session gets an isolated BrowserContext with randomised fingerprints
and optional proxy support.

Note: Bright Data browser support was removed in favour of Serper (Google Search
API) for discovery and Skyvern for browser-based job applications.
"""

from __future__ import annotations

import logging
import os
import platform
import signal
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from patchright.async_api import async_playwright, Browser, BrowserContext, Playwright, Error as PlaywrightError
from playwright.async_api import (
    async_playwright as cloud_async_playwright,
    Browser as CloudBrowser,
    BrowserContext as CloudBrowserContext,
    Playwright as CloudPlaywright,
    Error as CloudPlaywrightError,
)

from backend.browser.anti_detect.stealth import (
    apply_stealth,
    get_random_locale_timezone,
    get_random_user_agent,
    get_random_viewport,
    get_stealth_config,
)
from backend.browser import browserbase_client
from backend.shared.config import settings

logger = logging.getLogger(__name__)

# Persistent Chrome profile for building reCAPTCHA trust over time
_CHROME_PROFILE_DIR = Path.home() / ".jobhunter" / "chrome-profile"
_CDP_PORT = 9222



def _find_chrome_binary() -> Optional[str]:
    """Auto-detect the real Google Chrome binary on the system."""
    system = platform.system()
    candidates: list[str] = []

    if system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ]
    elif system == "Linux":
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ]
    elif system == "Windows":
        for base in [os.environ.get("PROGRAMFILES", ""), os.environ.get("PROGRAMFILES(X86)", "")]:
            if base:
                candidates.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))

    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


class BrowserManager:
    """Manages a single Chromium browser process and multiple isolated contexts.

    Supports two modes:
    - ``start()`` — launches Patchright's built-in Chromium (fast, good for scraping)
    - ``start_cdp()`` — launches real Chrome with CDP (bypasses reCAPTCHA)

    Usage::

        mgr = BrowserManager()
        await mgr.start_cdp()  # or await mgr.start()

        ctx_id, context = await mgr.new_context()
        page = await context.new_page()
        ...
        await mgr.close_context(ctx_id)

        await mgr.stop()
    """

    def __init__(self) -> None:
        self._playwright: Optional[Playwright | CloudPlaywright] = None
        self._browser: Optional[Browser | CloudBrowser] = None
        self._contexts: Dict[str, BrowserContext | CloudBrowserContext] = {}
        self._running: bool = False
        self._chrome_process: Optional[subprocess.Popen] = None
        self._launched_chrome: bool = False
        self._mode: str = "patchright"  # "patchright", "cdp" or "browserbase"
        self._bb_session: Optional[browserbase_client.BrowserbaseSession] = None
        self._bb_config: Optional[browserbase_client.BrowserbaseConfig] = None
        self.stagehand = None
        self._stagehand_cleanup = None
        self._allow_employer_applications = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, headless: Optional[bool] = None) -> None:
        """Launch Patchright's built-in Chromium (default mode)."""
        if self._running:
            logger.warning("BrowserManager.start() called but already running")
            return

        logger.info("Starting Patchright browser engine")
        self._playwright = await async_playwright().start()

        stealth_cfg = get_stealth_config()

        launch_kwargs: dict = {
            "headless": headless if headless is not None else stealth_cfg["headless"],
            "args": stealth_cfg["args"],
            "ignore_default_args": stealth_cfg["ignore_default_args"],
        }
        if stealth_cfg.get("slow_mo"):
            launch_kwargs["slow_mo"] = stealth_cfg["slow_mo"]

        self._browser = await self._playwright.chromium.launch(**launch_kwargs)
        self._running = True
        self._mode = "patchright"
        logger.info("Browser engine started (pid=%s)", self._browser.contexts)

    async def start_cdp(self, headless: bool = False) -> None:
        """Launch real Chrome with CDP and connect Playwright to it.

        This uses the user's actual Chrome binary with a persistent profile,
        which builds reCAPTCHA trust over time. The persistent profile is
        stored at ~/.jobhunter/chrome-profile/ and reused across sessions.
        """
        if self._running:
            logger.warning("BrowserManager.start_cdp() called but already running")
            return

        chrome_path = _find_chrome_binary()
        if not chrome_path:
            logger.warning("Chrome not found — falling back to Patchright")
            await self.start(headless=headless)
            return

        cdp_url = f"http://127.0.0.1:{_CDP_PORT}"
        version_info = await self._wait_for_cdp_endpoint(cdp_url, attempts=3, sleep_seconds=1)
        if version_info:
            logger.info("Reusing existing Chrome CDP endpoint: %s", version_info.get("Browser", "unknown"))
        else:
            version_info = await self._launch_chrome_for_cdp(chrome_path, cdp_url, headless=headless)
            if not version_info:
                await self.start(headless=headless)
                return

        connect_error = await self._connect_to_cdp_browser(cdp_url)
        if connect_error is None:
            return

        logger.warning("CDP connection failed (%s) — attempting clean Chrome restart", connect_error)
        await self._reset_cdp_listener()

        version_info = await self._launch_chrome_for_cdp(chrome_path, cdp_url, headless=headless)
        if not version_info:
            await self.start(headless=headless)
            return

        connect_error = await self._connect_to_cdp_browser(cdp_url)
        if connect_error is None:
            return

        logger.warning("CDP connection failed after clean restart (%s) — falling back to Patchright", connect_error)
        self._kill_chrome()
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        await self.start(headless=headless)

    async def start_browserbase(
        self,
        *,
        context_id: Optional[str] = None,
        persist: bool = True,
        proxies: Optional[bool] = None,
        config: Optional[browserbase_client.BrowserbaseConfig] = None,
        use_stagehand: bool = False,
    ) -> None:
        """Create a Browserbase cloud session and connect Playwright to it over CDP.

        With *context_id*, the session starts with that Context's cookies and
        storage (a persisted login) and writes them back on close when
        *persist* is true.  *config* carries a user's own Browserbase
        credentials; without it the env settings apply.  Bot detection and
        proxies are Browserbase's job in this mode, so no local stealth or
        proxy configuration applies.
        """
        if self._running:
            logger.warning("BrowserManager.start_browserbase() called but already running")
            return

        self._bb_config = config
        if use_stagehand:
            from backend.browser.stagehand_session import launch_stagehand
            self.stagehand, bb_session, self._stagehand_cleanup = await launch_stagehand(config, context_id)
        else:
            bb_session = await browserbase_client.create_session(
                context_id=context_id, persist=persist, proxies=proxies, config=config,
            )
        try:
            # Browserbase manages stealth and CAPTCHA solving. Patchright's
            # modified Runtime/Console protocol is only for local browsers.
            self._playwright = await cloud_async_playwright().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(
                bb_session.connect_url, timeout=45_000,
            )
        except BaseException:
            # Task cancellation also owns cleanup: _running is not set yet, so
            # stop() cannot release this newly allocated cloud session for us.
            if self._stagehand_cleanup:
                try:
                    await self._stagehand_cleanup.aclose()
                except Exception as exc:
                    logger.warning("Stagehand cleanup failed (%s)", type(exc).__name__)
                self._stagehand_cleanup = None
                self.stagehand = None
            await browserbase_client.release_session(bb_session.id, config=config)
            if self._playwright:
                await self._playwright.stop()
            self._playwright = None
            raise
        if self.stagehand:
            from backend.browser.captcha_monitor import CaptchaMonitor
            monitor = CaptchaMonitor(session_id=bb_session.id)
            # A context-level read-only event hook covers existing tabs AND popups.
            # Install before application navigation so challenge starts are not lost.
            for browser_context in self._browser.contexts:
                browser_context.on("console", lambda message: monitor.record(message.text))
            self.stagehand._jobhunter_captcha_monitor = monitor
        self._bb_session = bb_session
        self._running = True
        self._mode = "browserbase"
        logger.info(
            "Connected to Browserbase session %s (context=%s)",
            bb_session.id, context_id or "none",
        )

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def browserbase_session_id(self) -> Optional[str]:
        return self._bb_session.id if self._bb_session else None

    @property
    def live_view_url(self) -> Optional[str]:
        """Browserbase Live View URL for the running session (None in other modes)."""
        return self._bb_session.live_view_url if self._bb_session else None

    async def start_for_task(
        self,
        *,
        board: Optional[str] = None,
        purpose: str = "apply",
        headless: Optional[bool] = None,
        user_id: Optional[str] = None,
    ) -> None:
        """Start the best browser backend for the requested task.

        In Browserbase mode *user_id* selects that user's saved API key,
        project, proxy preference and per-board Context ids (Settings UI),
        layered over the ``BROWSERBASE_*`` env settings.
        """
        resolved_headless = settings.BROWSER_HEADLESS if headless is None else headless
        self._allow_employer_applications = purpose == "apply_external"
        if settings.INDEED_ONLY and settings.BROWSER_MODE != "browserbase":
            raise RuntimeError("Indeed-only mode requires BROWSER_MODE=browserbase")
        if settings.BROWSER_MODE == "browserbase":
            config = browserbase_client.config_for_user(user_id)
            context_id = browserbase_client.context_id_for_board(board, config)
            use_stagehand = purpose in ("apply", "apply_external", "hydrate") and str(getattr(board, "value", board)).lower() == "indeed"
            await self.start_browserbase(context_id=context_id, config=config, use_stagehand=use_stagehand)
        elif settings.BROWSER_MODE == "cdp":
            await self.start_cdp(headless=resolved_headless)
        else:
            await self.start(headless=resolved_headless)

    def _kill_chrome(self) -> None:
        """Terminate the Chrome process we launched."""
        if self._chrome_process:
            try:
                self._chrome_process.terminate()
                self._chrome_process.wait(timeout=5)
            except Exception:
                try:
                    self._chrome_process.kill()
                except Exception:
                    pass
            self._chrome_process = None
        self._launched_chrome = False

    async def stop(self) -> None:
        """Gracefully shut down all contexts and the browser process."""
        if not self._running:
            return

        logger.info("Stopping BrowserManager -- closing %d contexts", len(self._contexts))

        if self._stagehand_cleanup:
            try:
                await self._stagehand_cleanup.aclose()
            except Exception as exc:
                logger.warning("Stagehand cleanup failed (%s); continuing browser release", type(exc).__name__)
            finally:
                self._stagehand_cleanup = None
                self.stagehand = None

        # Close all open contexts first
        for ctx_id in list(self._contexts):
            await self.close_context(ctx_id)

        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

        if self._bb_session:
            # Closing the CDP connection ends the session and, with persist=True,
            # flushes cookies to the Context.  The release call is belt and braces.
            await browserbase_client.release_session(self._bb_session.id, config=self._bb_config)
            self._bb_session = None

        # Keep an existing Chrome debugger alive across runs to preserve session
        # state and avoid repeated profile/port contention on ATS flows.
        if self._launched_chrome:
            logger.info("Leaving launched Chrome CDP process running on port %d for reuse", _CDP_PORT)
            self._chrome_process = None
            self._launched_chrome = False

        self._running = False
        logger.info("BrowserManager stopped")

    # ------------------------------------------------------------------
    # Context management
    # ------------------------------------------------------------------

    async def new_context(
        self,
        proxy: Optional[str] = None,
    ) -> tuple[str, BrowserContext | CloudBrowserContext]:
        """Create a new isolated BrowserContext with anti-detection settings.

        In CDP mode, if the browser already has a default context, reuse it
        (Chrome CDP exposes existing contexts rather than creating new ones).
        """
        if not self._running or self._browser is None:
            raise RuntimeError("BrowserManager is not running. Call start() first.")

        ctx_id = uuid4().hex[:12]

        # In CDP and Browserbase modes, reuse the default context: Browserbase
        # loads the persisted Context's cookies into it, and Chrome CDP exposes
        # existing contexts rather than creating new ones.
        if self._mode in ("cdp", "browserbase") and self._browser.contexts:
            context = self._browser.contexts[0]
            if settings.INDEED_ONLY:
                from backend.browser.indeed_policy import is_indeed_url
                from backend.browser.application_routing import is_public_application_url, resolves_publicly
                context._jobhunter_external_redirect = None

                async def restrict_navigation(route):
                    request = route.request
                    if (not request.is_navigation_request() or is_indeed_url(request.url)
                            or (self._allow_employer_applications and await resolves_publicly(request.url))):
                        await route.fallback()
                        return
                    try:
                        is_child_frame = request.frame.parent_frame is not None
                    except (PlaywrightError, CloudPlaywrightError):
                        # Initial popup navigation may precede frame creation.
                        # Unknown frames cannot authorize an external navigation.
                        is_child_frame = False
                    if is_child_frame:
                        await route.fallback()  # Allow embedded CAPTCHA providers.
                    else:
                        if is_public_application_url(request.url):
                            context._jobhunter_external_redirect = request.url
                        await route.abort()

                await context.route("**/*", restrict_navigation)
            self._contexts[ctx_id] = context
            if self._mode == "browserbase" and settings.BROWSERBASE_BLOCK_MEDIA and not settings.INDEED_ONLY:
                await self._block_media(context)
            logger.info("Reusing %s default context as %s", self._mode, ctx_id)
            return ctx_id, context

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
            # Parse proxy URL into Playwright's expected format
            from urllib.parse import urlparse
            parsed = urlparse(effective_proxy)
            proxy_config: dict = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"}
            if parsed.username:
                username = parsed.username
                # BrightData sticky session — same residential IP for entire context
                if "brd.superproxy.io" in effective_proxy:
                    import uuid as _uuid
                    stick_id = _uuid.uuid4().hex[:8]
                    username = f"{username}-session-{stick_id}"
                proxy_config["username"] = username
            if parsed.password:
                proxy_config["password"] = parsed.password
            ctx_options["proxy"] = proxy_config
            logger.info("Context %s using proxy %s:%s", ctx_id, parsed.hostname, parsed.port)

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

    @staticmethod
    async def _block_media(context: BrowserContext) -> None:
        """Abort image, font and media requests to save proxy bandwidth.

        Form filling never needs them; a job page is mostly images by bytes.
        """
        async def _route(route: Any) -> None:
            if route.request.resource_type in ("image", "media", "font"):
                await route.abort()
            else:
                await route.fallback()

        try:
            await context.route("**/*", _route)
        except Exception:
            logger.debug("Could not install media-blocking route", exc_info=True)

    async def close_context(self, context_id: str) -> None:
        """Close and remove the context identified by *context_id*.

        Silently does nothing if the context has already been closed or does
        not exist.  In CDP mode, doesn't close the default context (Chrome
        would exit).
        """
        context = self._contexts.pop(context_id, None)
        if context is None:
            logger.debug("Context %s not found (already closed?)", context_id)
            return

        # In CDP mode, don't close the default context — just remove tracking
        if self._mode in ("cdp", "browserbase") and self._browser and context in self._browser.contexts:
            logger.info("Released %s default context %s (not closing it)", self._mode, context_id)
            return

        try:
            await context.close()
            logger.info("Closed browser context %s", context_id)
        except Exception:
            logger.warning("Error closing context %s (may already be closed)", context_id, exc_info=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _wait_for_cdp_endpoint(
        self,
        cdp_url: str,
        attempts: int,
        sleep_seconds: int,
    ) -> Optional[dict[str, Any]]:
        import asyncio
        import aiohttp

        for _ in range(attempts):
            try:
                async with aiohttp.ClientSession() as http:
                    async with http.get(
                        f"{cdp_url}/json/version",
                        timeout=aiohttp.ClientTimeout(total=2),
                    ) as resp:
                        if resp.status == 200:
                            return await resp.json()
            except Exception:
                pass
            await asyncio.sleep(sleep_seconds)
        return None

    async def _launch_chrome_for_cdp(
        self,
        chrome_path: str,
        cdp_url: str,
        headless: bool,
    ) -> Optional[dict[str, Any]]:
        _CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

        chrome_args = [
            chrome_path,
            f"--remote-debugging-port={_CDP_PORT}",
            f"--user-data-dir={_CHROME_PROFILE_DIR}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-hang-monitor",
            "--disable-popup-blocking",
            "--disable-infobars",
            "--window-size=1920,1080",
        ]
        if headless:
            chrome_args.append("--headless=new")

        logger.info(
            "Launching Chrome CDP: %s (port=%d, profile=%s)",
            chrome_path,
            _CDP_PORT,
            _CHROME_PROFILE_DIR,
        )

        try:
            self._chrome_process = subprocess.Popen(
                chrome_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._launched_chrome = True
        except Exception as exc:
            logger.warning("Failed to launch Chrome (%s) — falling back to Patchright", exc)
            return None

        version_info = await self._wait_for_cdp_endpoint(cdp_url, attempts=20, sleep_seconds=1)
        if not version_info:
            logger.warning("Chrome CDP didn't respond after launch — falling back to Patchright")
            self._kill_chrome()
            return None

        logger.info("Chrome CDP ready: %s", version_info.get("Browser", "unknown"))
        return version_info

    async def _connect_to_cdp_browser(self, cdp_url: str) -> Optional[Exception]:
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

        self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(
                cdp_url,
                timeout=45_000,
            )
            self._running = True
            self._mode = "cdp"
            logger.info("Connected to Chrome via CDP (contexts=%d)", len(self._browser.contexts))
            return None
        except Exception as exc:
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            return exc

    async def _reset_cdp_listener(self) -> None:
        self._kill_chrome()
        for pid in self._find_cdp_listener_pids():
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                continue
            except Exception:
                logger.debug("Failed to terminate CDP listener pid=%s", pid, exc_info=True)

    def _find_cdp_listener_pids(self) -> list[int]:
        try:
            result = subprocess.run(
                ["lsof", "-ti", f"tcp:{_CDP_PORT}"],
                check=False,
                capture_output=True,
                text=True,
            )
        except Exception:
            return []

        pids: list[int] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                pids.append(int(line))
            except ValueError:
                continue
        return pids

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

    @property
    def mode(self) -> str:
        """Return the current browser mode: 'patchright' or 'cdp'."""
        return self._mode
