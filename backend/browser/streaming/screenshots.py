# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""CDP screenshot capture loop for the live screenshot feed.

Captures JPEG screenshots from a Playwright page at 1-2 FPS and publishes
each frame (base64-encoded) to a Redis pub/sub channel.  The frontend
WebSocket handler subscribes to the channel and forwards frames to the
browser canvas.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Optional

from playwright.async_api import Page

from backend.shared.redis_client import RedisClient

logger = logging.getLogger(__name__)

# Screenshot quality (JPEG, 0-100).  50 gives ~40-100 KB per frame.
_JPEG_QUALITY = 50

# Target frames per second.  1-2 FPS is sufficient for status monitoring.
_TARGET_FPS = 2

# Interval between frames in seconds.
_FRAME_INTERVAL = 1.0 / _TARGET_FPS


class ScreenshotStreamer:
    """Captures screenshots from a Playwright page and streams them via Redis.

    Usage::

        streamer = ScreenshotStreamer()
        await streamer.start(page, session_id, redis_client)
        # ... browser automation continues ...
        await streamer.stop()
    """

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._running: bool = False
        self._page: Optional[Page] = None
        self._session_id: Optional[str] = None
        self._redis: Optional[RedisClient] = None
        self._frame_count: int = 0

    @property
    def is_running(self) -> bool:
        """Return ``True`` if the capture loop is active."""
        return self._running and self._task is not None and not self._task.done()

    async def start(
        self,
        page: Page,
        session_id: str,
        redis_client: RedisClient,
    ) -> None:
        """Start the screenshot capture loop.

        Parameters
        ----------
        page:
            The Playwright ``Page`` to capture.
        session_id:
            Unique session identifier used for the Redis channel name.
        redis_client:
            A connected ``RedisClient`` instance for publishing frames.
        """
        if self.is_running:
            logger.warning(
                "Screenshot streamer already running for session %s",
                self._session_id,
            )
            return

        self._page = page
        self._session_id = session_id
        self._redis = redis_client
        self._running = True
        self._frame_count = 0

        self._task = asyncio.create_task(
            self._capture_loop(),
            name=f"screenshot-stream-{session_id}",
        )
        logger.info(
            "Screenshot streamer started for session %s at %d FPS",
            session_id,
            _TARGET_FPS,
        )

    async def stop(self) -> None:
        """Stop the capture loop and clean up."""
        self._running = False

        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info(
            "Screenshot streamer stopped for session %s (%d frames captured)",
            self._session_id,
            self._frame_count,
        )
        self._page = None
        self._session_id = None
        self._redis = None

    async def _capture_loop(self) -> None:
        """Internal loop that captures and publishes screenshots."""
        channel = f"screenshots:{self._session_id}"

        while self._running:
            loop_start = time.monotonic()

            try:
                if self._page is None or self._page.is_closed():
                    logger.warning("Page closed -- stopping screenshot stream")
                    self._running = False
                    break

                # Capture screenshot as JPEG bytes
                screenshot_bytes = await self._page.screenshot(
                    type="jpeg",
                    quality=_JPEG_QUALITY,
                    # full_page=False -- only visible viewport for speed
                )

                # Encode to base64 for JSON transport
                frame_b64 = base64.b64encode(screenshot_bytes).decode("ascii")

                # Get current URL for context
                current_url = ""
                try:
                    current_url = self._page.url
                except Exception:
                    pass

                # Build frame payload
                frame_data = {
                    "frame": frame_b64,
                    "url": current_url,
                    "timestamp": time.time(),
                    "frame_number": self._frame_count,
                    "size_bytes": len(screenshot_bytes),
                }

                # Publish to Redis
                if self._redis is not None:
                    await self._redis.publish_event(channel, frame_data)

                self._frame_count += 1

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug("Screenshot capture error: %s", exc)
                # Don't crash the loop on transient errors
                await asyncio.sleep(0.5)
                continue

            # Maintain target FPS by sleeping for the remainder of the interval
            elapsed = time.monotonic() - loop_start
            sleep_time = max(0, _FRAME_INTERVAL - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    async def capture_single(self) -> Optional[str]:
        """Capture a single screenshot and return it as base64 JPEG.

        Useful for on-demand snapshots (e.g., verification agent).
        Returns ``None`` if the page is not available.
        """
        if self._page is None or self._page.is_closed():
            return None

        try:
            screenshot_bytes = await self._page.screenshot(
                type="jpeg",
                quality=_JPEG_QUALITY,
            )
            return base64.b64encode(screenshot_bytes).decode("ascii")
        except Exception as exc:
            logger.warning("Single screenshot capture failed: %s", exc)
            return None
