# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""On-demand noVNC setup and teardown for live takeover mode.

Manages Xvfb (virtual framebuffer), x11vnc (VNC server), and websockify
(WebSocket-to-VNC bridge) processes.  These are only spun up when a user
clicks "Take Control" and torn down when they release control, to avoid
the resource cost of running VNC per-user at all times.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Port ranges for dynamically assigned VNC / websockify ports.
# Each session gets a unique pair to support concurrent takeovers.
_VNC_PORT_BASE = 5900
_WEBSOCKIFY_PORT_BASE = 6080

# Track session port assignments to avoid collisions.
_port_offset: int = 0


@dataclass
class _VNCSession:
    """Internal state for a running VNC session."""

    session_id: str
    display: str
    vnc_port: int
    websockify_port: int
    xvfb_pid: Optional[int] = None
    x11vnc_pid: Optional[int] = None
    websockify_pid: Optional[int] = None
    xvfb_proc: Optional[asyncio.subprocess.Process] = None
    x11vnc_proc: Optional[asyncio.subprocess.Process] = None
    websockify_proc: Optional[asyncio.subprocess.Process] = None


class VNCManager:
    """Manages on-demand noVNC sessions for browser takeover.

    Usage::

        vnc = VNCManager()
        info = await vnc.start_vnc("session-123")
        # info == {"vnc_url": "ws://host:6080/websockify", "display": ":99", ...}
        # ... user interacts via noVNC ...
        await vnc.stop_vnc("session-123")
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, _VNCSession] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_vnc(
        self,
        session_id: str,
        display: str = ":99",
        resolution: str = "1920x1080x24",
    ) -> Dict[str, str | int]:
        """Start Xvfb + x11vnc + websockify for *session_id*.

        Parameters
        ----------
        session_id:
            Unique session identifier.
        display:
            X display number (e.g. ``:99``).
        resolution:
            Xvfb screen resolution (``WxHxD``).

        Returns
        -------
        dict
            Connection details: ``vnc_url``, ``display``, ``vnc_port``,
            ``websockify_port``.
        """
        if session_id in self._sessions:
            existing = self._sessions[session_id]
            logger.warning(
                "VNC session already running for %s on display %s",
                session_id,
                existing.display,
            )
            return self._connection_info(existing)

        global _port_offset
        vnc_port = _VNC_PORT_BASE + _port_offset
        ws_port = _WEBSOCKIFY_PORT_BASE + _port_offset
        _port_offset += 1

        vnc_session = _VNCSession(
            session_id=session_id,
            display=display,
            vnc_port=vnc_port,
            websockify_port=ws_port,
        )

        try:
            # 1. Start Xvfb (virtual framebuffer)
            xvfb_cmd = [
                "Xvfb", display,
                "-screen", "0", resolution,
                "-ac",                    # disable access control
                "+extension", "RANDR",    # support resolution changes
                "-nolisten", "tcp",
            ]
            logger.info("Starting Xvfb: %s", " ".join(xvfb_cmd))
            vnc_session.xvfb_proc = await asyncio.create_subprocess_exec(
                *xvfb_cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            vnc_session.xvfb_pid = vnc_session.xvfb_proc.pid

            # Give Xvfb time to initialise
            await asyncio.sleep(1.0)

            # 2. Start x11vnc (VNC server connected to the virtual display)
            x11vnc_cmd = [
                "x11vnc",
                "-display", display,
                "-rfbport", str(vnc_port),
                "-nopw",                  # no password (internal network only)
                "-forever",               # don't exit after first client disconnects
                "-shared",                # allow multiple connections
                "-noxdamage",             # avoid rendering glitches
                "-cursor", "arrow",
                "-xkb",
            ]
            logger.info("Starting x11vnc: %s", " ".join(x11vnc_cmd))
            vnc_session.x11vnc_proc = await asyncio.create_subprocess_exec(
                *x11vnc_cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            vnc_session.x11vnc_pid = vnc_session.x11vnc_proc.pid

            await asyncio.sleep(0.5)

            # 3. Start websockify (WebSocket bridge for noVNC)
            websockify_cmd = [
                "websockify",
                "--web", "/usr/share/novnc",  # serve noVNC client files
                str(ws_port),
                f"localhost:{vnc_port}",
            ]
            logger.info("Starting websockify: %s", " ".join(websockify_cmd))
            vnc_session.websockify_proc = await asyncio.create_subprocess_exec(
                *websockify_cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            vnc_session.websockify_pid = vnc_session.websockify_proc.pid

            self._sessions[session_id] = vnc_session

            logger.info(
                "VNC session started for %s -- display=%s, vnc_port=%d, ws_port=%d",
                session_id,
                display,
                vnc_port,
                ws_port,
            )

            return self._connection_info(vnc_session)

        except Exception as exc:
            logger.error("Failed to start VNC for session %s: %s", session_id, exc)
            # Clean up any processes that did start
            await self._kill_session(vnc_session)
            raise RuntimeError(f"VNC setup failed: {exc}") from exc

    async def stop_vnc(self, session_id: str) -> None:
        """Tear down all VNC processes for *session_id*."""
        vnc_session = self._sessions.pop(session_id, None)
        if vnc_session is None:
            logger.debug("No VNC session found for %s -- nothing to stop", session_id)
            return

        await self._kill_session(vnc_session)
        logger.info("VNC session stopped for %s", session_id)

    def get_vnc_url(self, session_id: str) -> Optional[str]:
        """Return the websockify URL for the noVNC client, or ``None``.

        The returned URL is suitable for connecting a noVNC JavaScript
        client in the frontend.
        """
        vnc_session = self._sessions.get(session_id)
        if vnc_session is None:
            return None
        # In production the host would be the container's public hostname.
        # For local dev, use localhost.
        host = os.environ.get("VNC_HOST", "localhost")
        return f"ws://{host}:{vnc_session.websockify_port}/websockify"

    def is_running(self, session_id: str) -> bool:
        """Return ``True`` if a VNC session is active for *session_id*."""
        return session_id in self._sessions

    async def stop_all(self) -> None:
        """Tear down all active VNC sessions.  Called during shutdown."""
        session_ids = list(self._sessions.keys())
        for sid in session_ids:
            await self.stop_vnc(sid)
        logger.info("All VNC sessions stopped")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _connection_info(self, session: _VNCSession) -> Dict[str, str | int]:
        """Build the connection info dict for a VNC session."""
        host = os.environ.get("VNC_HOST", "localhost")
        return {
            "vnc_url": f"ws://{host}:{session.websockify_port}/websockify",
            "display": session.display,
            "vnc_port": session.vnc_port,
            "websockify_port": session.websockify_port,
            "session_id": session.session_id,
        }

    async def _kill_session(self, session: _VNCSession) -> None:
        """Terminate all processes in a VNC session."""
        for name, proc in [
            ("websockify", session.websockify_proc),
            ("x11vnc", session.x11vnc_proc),
            ("Xvfb", session.xvfb_proc),
        ]:
            if proc is None:
                continue
            try:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                logger.debug(
                    "Stopped %s (pid=%d) for session %s",
                    name,
                    proc.pid,
                    session.session_id,
                )
            except ProcessLookupError:
                pass  # Already exited
            except Exception as exc:
                logger.warning(
                    "Error stopping %s for session %s: %s",
                    name,
                    session.session_id,
                    exc,
                )
