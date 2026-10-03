# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Capture a job-board login into a persisted Browserbase Context.

Flow (mirrors the owner's login-capture script):

1. create a Context (``POST /v1/contexts``)
2. start a session with ``browserSettings.context = {id, persist: true}``
3. hand the Live View URL to the user so they can sign in by hand
4. poll the browser's cookies until the board's login cookie appears
5. close and release the session, then wait for persisted storage to settle
6. store the Context id for that board on the user's Browserbase settings

Captures are tracked in-process; they are short-lived (bounded by the
Browserbase session timeout) and a restart simply drops the pending ones.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from playwright.async_api import async_playwright

from backend.browser import browserbase_client as bbc

logger = logging.getLogger(__name__)

# board -> (login cookie name, cookie domain suffix, URL to open for the user).
# Indeed's PPID cookie was confirmed live on 2026-10-03 (persisted Indeed
# context opened myjobs.indeed.com/saved signed in). Other boards are not
# listed until their login cookie has been checked the same way; LinkedIn is
# deliberately absent (discovery-only, account-ban risk).
BOARD_LOGIN: Dict[str, Tuple[str, str, str]] = {
    "indeed": ("PPID", "indeed.com", "https://secure.indeed.com/account/login"),
}

COOKIE_POLL_SECONDS = 2.0
SETTLE_SECONDS = 4.0  # allow Browserbase to persist storage after release
DEFAULT_TIMEOUT_SECONDS = 600

StoreContextFn = Callable[[str, str, str], Any]


@dataclass
class LoginCapture:
    id: str
    user_id: str
    board: str
    context_id: str
    browserbase_session_id: str
    live_view_url: Optional[str]
    status: str = "waiting"  # waiting | captured | timeout | error | cancelled
    error: Optional[str] = None
    started_at: float = field(default_factory=time.monotonic)
    finished_at: Optional[float] = None

    def public(self) -> Dict[str, Any]:
        return {
            "capture_id": self.id,
            "board": self.board,
            "status": self.status,
            "context_id": self.context_id if self.status == "captured" else None,
            "browserbase_session_id": self.browserbase_session_id,
            "live_view_url": self.live_view_url,
            "error": self.error,
            "elapsed_seconds": int((self.finished_at or time.monotonic()) - self.started_at),
        }


def _has_login_cookie(cookies: Any, name: str, domain_suffix: str) -> bool:
    for cookie in cookies or []:
        if cookie.get("name") != name:
            continue
        domain = str(cookie.get("domain") or "").lstrip(".")
        if domain == domain_suffix or domain.endswith(f".{domain_suffix}"):
            return True
    return False


class LoginCaptureRegistry:
    """Starts and tracks login captures for this process."""

    def __init__(self) -> None:
        self._captures: Dict[str, LoginCapture] = {}
        self._tasks: Dict[str, asyncio.Task] = {}

    def get(self, capture_id: str, user_id: str) -> Optional[LoginCapture]:
        capture = self._captures.get(capture_id)
        if capture is None or capture.user_id != user_id:
            return None
        return capture

    def active_for(self, user_id: str, board: str) -> Optional[LoginCapture]:
        for capture in self._captures.values():
            if capture.user_id == user_id and capture.board == board and capture.status == "waiting":
                return capture
        return None

    async def start(
        self,
        *,
        user_id: str,
        board: str,
        config: bbc.BrowserbaseConfig,
        store_context: StoreContextFn,
        timeout_seconds: Optional[int] = None,
    ) -> LoginCapture:
        board = board.lower()
        if board not in BOARD_LOGIN:
            raise ValueError(
                f"Login capture is not available for {board!r}; supported: {sorted(BOARD_LOGIN)}"
            )
        if not config.configured:
            raise bbc.BrowserbaseError("Browserbase API key and project id must be configured first")

        existing = self.active_for(user_id, board)
        if existing:
            return existing

        context_id = await bbc.create_context(f"jobhunter-{board}-{user_id[:8]}", config=config)
        session = await bbc.create_session(
            context_id=context_id, persist=True, config=config,
            timeout=min(config.session_timeout, timeout_seconds or DEFAULT_TIMEOUT_SECONDS) + 60,
        )
        capture = LoginCapture(
            id=uuid.uuid4().hex,
            user_id=user_id,
            board=board,
            context_id=context_id,
            browserbase_session_id=session.id,
            live_view_url=session.live_view_url,
        )
        self._captures[capture.id] = capture
        self._tasks[capture.id] = asyncio.create_task(
            self._watch(capture, session, config, store_context,
                        timeout_seconds or DEFAULT_TIMEOUT_SECONDS)
        )
        logger.info(
            "Login capture %s started for user %s board %s (context %s, session %s)",
            capture.id, user_id, board, context_id, session.id,
        )
        return capture

    async def cancel(self, capture_id: str, user_id: str) -> Optional[LoginCapture]:
        capture = self.get(capture_id, user_id)
        if capture is None:
            return None
        task = self._tasks.get(capture_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        if capture.status == "waiting":
            capture.status = "cancelled"
            capture.finished_at = time.monotonic()
        return capture

    async def _watch(
        self,
        capture: LoginCapture,
        session: bbc.BrowserbaseSession,
        config: bbc.BrowserbaseConfig,
        store_context: StoreContextFn,
        timeout_seconds: int,
    ) -> None:
        cookie_name, domain_suffix, login_url = BOARD_LOGIN[capture.board]
        playwright = None
        browser = None
        released = False
        try:
            playwright = await async_playwright().start()
            browser = await playwright.chromium.connect_over_cdp(session.connect_url, timeout=45_000)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = context.pages[0] if context.pages else await context.new_page()
            try:
                await page.goto(login_url, wait_until="domcontentloaded", timeout=30_000)
            except Exception as exc:  # the user can still navigate by hand in the Live View
                logger.warning("Login capture %s: could not open %s: %s", capture.id, login_url, exc)

            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                cookies = await context.cookies()
                if _has_login_cookie(cookies, cookie_name, domain_suffix):
                    logger.info("Login capture %s: %s cookie present, settling", capture.id, cookie_name)
                    await browser.close()
                    browser = None
                    await bbc.release_session(session.id, config=config)
                    released = True
                    await asyncio.sleep(SETTLE_SECONDS)
                    result = store_context(capture.user_id, capture.board, capture.context_id)
                    if asyncio.iscoroutine(result):
                        await result
                    capture.status = "captured"
                    break
                await asyncio.sleep(COOKIE_POLL_SECONDS)
            else:
                capture.status = "timeout"
                capture.error = f"{cookie_name} cookie did not appear within {timeout_seconds}s"
        except asyncio.CancelledError:
            capture.status = "cancelled"
            raise
        except Exception as exc:
            capture.status = "error"
            capture.error = str(exc)[:300]
            logger.exception("Login capture %s failed", capture.id)
        finally:
            capture.finished_at = time.monotonic()
            if browser is not None:
                try:
                    await browser.close()
                except Exception:
                    logger.debug("Login capture %s: browser close failed", capture.id, exc_info=True)
            if playwright is not None:
                try:
                    await playwright.stop()
                except Exception:
                    logger.debug("Login capture %s: playwright stop failed", capture.id, exc_info=True)
            if not released:
                await bbc.release_session(session.id, config=config)
            logger.info("Login capture %s finished: %s", capture.id, capture.status)


registry = LoginCaptureRegistry()
