"""Screenshot Streamer -- captures periodic screenshots of browser activity.

Publishes base64-encoded screenshots via Redis pub/sub for the frontend
to display live browser activity when steering_mode is "screenshot".
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any, Optional

from backend.shared.config import settings

logger = logging.getLogger(__name__)


class ScreenshotStreamer:
    """Captures and publishes live screenshots from a Playwright page.

    Usage::

        streamer = ScreenshotStreamer(session_id="abc123")
        await streamer.start(page)
        ...
        await streamer.stop()
    """

    def __init__(
        self,
        session_id: str,
        interval_ms: int = 2000,
        quality: int = 50,
    ):
        self.session_id = session_id
        self.interval_ms = interval_ms
        self.quality = quality
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._redis: Any = None
        self._page: Any = None

    async def start(self, page: Any) -> None:
        """Start the screenshot capture loop.

        Parameters
        ----------
        page:
            The Playwright Page to capture.
        """
        if self._running:
            return

        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(settings.REDIS_URL)
            await self._redis.ping()
            logger.info("Redis connected for screenshot streaming")
        except Exception as exc:
            logger.warning("Redis not available -- screenshots will not be streamed: %s", exc)
            self._redis = None
            return

        self._page = page
        self._running = True
        if hasattr(page, "on"):
            try:
                page.on("close", self._handle_page_close)
            except Exception:
                logger.debug("Failed to attach page close handler", exc_info=True)
        self._task = asyncio.create_task(self._capture_loop(page))
        logger.info("Screenshot streamer started for session %s", self.session_id)

    async def stop(self) -> None:
        """Stop the capture loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        self._page = None
        if self._redis:
            await self._redis.close()
            self._redis = None

        logger.info("Screenshot streamer stopped for session %s", self.session_id)

    async def capture_once(self, page: Any) -> Optional[str]:
        """Capture a single screenshot and return as base64 string."""
        try:
            if hasattr(page, "is_closed") and page.is_closed():
                self._running = False
                return None
            screenshot_bytes = await page.screenshot(
                type="jpeg",
                quality=self.quality,
                full_page=False,
            )
            # Offload CPU-bound base64 encoding to thread pool
            return await asyncio.to_thread(
                lambda b: base64.b64encode(b).decode("utf-8"), screenshot_bytes
            )
        except Exception as exc:
            if exc.__class__.__name__ == "TargetClosedError":
                self._running = False
            logger.debug("Screenshot capture failed", exc_info=True)
            return None

    def _handle_page_close(self, *_args: Any) -> None:
        """Stop the loop when the underlying Playwright page closes."""
        self._running = False

    async def _safe_page_url(self, page: Any) -> str:
        try:
            return page.url
        except Exception:
            return ""

    async def _publish_frame(self, channel: str, b64: str, page: Any) -> None:
        if not self._redis:
            return
        payload = json.dumps({
            "session_id": self.session_id,
            "screenshot": b64,
            "url": await self._safe_page_url(page),
        })
        receivers = await self._redis.publish(channel, payload)
        logger.debug(
            "Published screenshot to %s (%d receivers, %d bytes)",
            channel,
            receivers,
            len(payload),
        )

    async def _sleep_interval(self) -> None:
        try:
            await asyncio.sleep(self.interval_ms / 1000)
        except asyncio.CancelledError:
            raise

    async def _capture_or_stop(self, page: Any) -> Optional[str]:
        try:
            return await self.capture_once(page)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("Screenshot capture failed", exc_info=True)
            return None

    async def _capture_loop(self, page: Any) -> None:
        """Internal loop that captures and publishes screenshots."""
        channel = f"screenshots:{self.session_id}"

        while self._running:
            try:
                b64 = await self._capture_or_stop(page)
                if b64:
                    await self._publish_frame(channel, b64, page)

                if not self._running:
                    break
                await self._sleep_interval()

            except asyncio.CancelledError:
                break
            except Exception:
                logger.debug("Screenshot loop error", exc_info=True)
                if hasattr(page, "is_closed") and page.is_closed():
                    self._running = False
                    break
                await asyncio.sleep(1)
