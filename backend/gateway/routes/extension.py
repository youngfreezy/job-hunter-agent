# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Chrome Extension WebSocket relay for CDP (Chrome DevTools Protocol).

Enables the user's Chrome browser (via our extension) to be controlled by
browser-use for job application form filling.  The extension connects via
WebSocket and relays CDP commands to/from chrome.debugger.

Two WebSocket endpoints:
  /ws/extension/connect?token=<jwt>  -- extension connects here
  /ws/extension/cdp/{user_id}        -- browser-use connects here (CDP protocol)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Dict, Optional

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect

from backend.shared.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["extension"])


# ---------------------------------------------------------------------------
# Connection Manager (singleton)
# ---------------------------------------------------------------------------


class ExtensionConnection:
    """Tracks a single extension's WebSocket + state."""

    __slots__ = ("ws", "user_id", "connected_at", "tab_id", "_pending")

    def __init__(self, ws: WebSocket, user_id: str) -> None:
        self.ws = ws
        self.user_id = user_id
        self.connected_at = time.time()
        self.tab_id: Optional[int] = None
        # Pending CDP responses keyed by message id
        self._pending: Dict[int, asyncio.Future] = {}

    async def send_cdp_command(
        self, method: str, params: dict | None = None, msg_id: int = 0,
    ) -> dict:
        """Send a CDP command to the extension and wait for the response."""
        timeout = get_settings().EXTENSION_CDP_TIMEOUT
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = fut
        try:
            await self.ws.send_json({
                "type": "cdp_command",
                "id": msg_id,
                "method": method,
                "params": params or {},
            })
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"CDP command {method} timed out after {timeout}s")
        finally:
            self._pending.pop(msg_id, None)

    def resolve(self, msg_id: int, result: dict) -> None:
        """Resolve a pending CDP response."""
        fut = self._pending.get(msg_id)
        if fut and not fut.done():
            fut.set_result(result)

    def reject(self, msg_id: int, error: str) -> None:
        """Reject a pending CDP command with an error."""
        fut = self._pending.get(msg_id)
        if fut and not fut.done():
            fut.set_exception(RuntimeError(error))


class ExtensionConnectionManager:
    """Manages per-user extension WebSocket connections."""

    def __init__(self) -> None:
        self._connections: Dict[str, ExtensionConnection] = {}

    def register(self, user_id: str, conn: ExtensionConnection) -> None:
        old = self._connections.get(user_id)
        if old:
            logger.info("Replacing existing extension connection for user %s", user_id)
        self._connections[user_id] = conn
        logger.info("Extension connected for user %s", user_id)

    def unregister(self, user_id: str) -> None:
        self._connections.pop(user_id, None)
        logger.info("Extension disconnected for user %s", user_id)

    def is_connected(self, user_id: str) -> bool:
        return user_id in self._connections

    def get_connection(self, user_id: str) -> Optional[ExtensionConnection]:
        return self._connections.get(user_id)

    def get_cdp_ws_url(self, user_id: str) -> Optional[str]:
        """Return the internal CDP relay WebSocket URL for browser-use."""
        if not self.is_connected(user_id):
            return None
        settings = get_settings()
        base = settings.BACKEND_PUBLIC_URL or "http://localhost:8000"
        ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
        return f"{ws_base}/ws/extension/cdp/{user_id}"


# Module-level singleton
extension_manager = ExtensionConnectionManager()


# ---------------------------------------------------------------------------
# REST: Extension status check
# ---------------------------------------------------------------------------

@router.get("/api/extension/status")
async def extension_status(request: Request):
    """Check if the current user has a Chrome extension connected."""
    from backend.gateway.deps import get_current_user
    try:
        user = get_current_user(request)
    except Exception:
        return {"connected": False}
    return {
        "connected": extension_manager.is_connected(user["id"]),
    }


# ---------------------------------------------------------------------------
# JWT verification for WebSocket (reuses NextAuth secret)
# ---------------------------------------------------------------------------

def _verify_ws_token(token: str) -> Optional[str]:
    """Verify JWT token and return user email, or None."""
    secret = get_settings().NEXTAUTH_SECRET
    if not secret:
        logger.error("NEXTAUTH_SECRET not configured")
        return None
    try:
        from backend.gateway.middleware.jwt_auth import decrypt_nextauth_jwt
        payload = decrypt_nextauth_jwt(token, secret)
        return payload.get("email")
    except Exception as exc:
        logger.debug("Extension JWT verification failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# WebSocket: Extension connects here
# ---------------------------------------------------------------------------

@router.websocket("/ws/extension/connect")
async def extension_connect(ws: WebSocket, token: str = Query(...)):
    """Extension WebSocket endpoint.

    The extension authenticates with a JWT token, then relays CDP commands
    between the backend and chrome.debugger in the user's browser.
    """
    email = _verify_ws_token(token)
    if not email:
        await ws.close(code=4001, reason="Invalid or expired token")
        return

    from backend.shared.billing_store import get_or_create_user
    user = get_or_create_user(email)
    user_id = user["id"]

    await ws.accept()
    conn = ExtensionConnection(ws, user_id)
    extension_manager.register(user_id, conn)

    try:
        await ws.send_json({"type": "connected", "user_id": user_id})

        while True:
            data = await ws.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "cdp_response":
                # Extension responding to a CDP command we sent
                conn.resolve(data.get("id", 0), data.get("result", {}))

            elif msg_type == "cdp_error":
                conn.reject(data.get("id", 0), data.get("error", "Unknown CDP error"))

            elif msg_type == "cdp_event":
                # CDP event from extension (Page.loadEventFired, etc.)
                # Forward to any listening CDP consumers
                pass  # TODO: forward to cdp consumer websocket

            elif msg_type == "tab_ready":
                conn.tab_id = data.get("tabId")
                logger.info("Extension tab ready: %s for user %s", conn.tab_id, user_id)

            elif msg_type == "ping":
                await ws.send_json({"type": "pong"})

            else:
                logger.debug("Unknown extension message type: %s", msg_type)

    except WebSocketDisconnect:
        logger.info("Extension disconnected for user %s", user_id)
    except Exception:
        logger.exception("Extension WebSocket error for user %s", user_id)
    finally:
        extension_manager.unregister(user_id)


# ---------------------------------------------------------------------------
# WebSocket: browser-use connects here (CDP protocol relay)
# ---------------------------------------------------------------------------

@router.websocket("/ws/extension/cdp/{user_id}")
async def cdp_relay(ws: WebSocket, user_id: str):
    """CDP relay endpoint that browser-use connects to.

    Speaks the CDP WebSocket protocol: receives JSON CDP commands from
    browser-use, forwards them to the extension, and relays responses back.
    This makes the endpoint look like a native CDP WebSocket to browser-use.
    """
    conn = extension_manager.get_connection(user_id)
    if not conn:
        await ws.close(code=4004, reason="No extension connected for this user")
        return

    await ws.accept()
    logger.info("CDP consumer connected for user %s", user_id)

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_id = msg.get("id", 0)
            method = msg.get("method", "")
            params = msg.get("params", {})

            try:
                result = await conn.send_cdp_command(method, params, msg_id)
                # Send CDP response back to browser-use
                await ws.send_text(json.dumps({
                    "id": msg_id,
                    "result": result,
                }))
            except TimeoutError as exc:
                await ws.send_text(json.dumps({
                    "id": msg_id,
                    "error": {"message": str(exc)},
                }))
            except RuntimeError as exc:
                await ws.send_text(json.dumps({
                    "id": msg_id,
                    "error": {"message": str(exc)},
                }))
            except Exception as exc:
                logger.exception("CDP relay error for %s", method)
                await ws.send_text(json.dumps({
                    "id": msg_id,
                    "error": {"message": f"Relay error: {exc}"},
                }))

    except WebSocketDisconnect:
        logger.info("CDP consumer disconnected for user %s", user_id)
    except Exception:
        logger.exception("CDP relay error for user %s", user_id)
