"""WebSocket route for live screenshot streaming and chat.

Bridges Redis pub/sub (where ScreenshotStreamer publishes) to WebSocket
clients in the browser. Also handles chat/steering messages from the
Take Control tab.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.browser.streaming.takeover_registry import get_active_page
from backend.shared.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/sessions/{session_id}")
async def session_websocket(websocket: WebSocket, session_id: str):
    """Stream screenshots from Redis pub/sub to the browser over WebSocket.

    Also accepts incoming messages for steering/chat.
    """
    await websocket.accept()
    logger.info("WebSocket connected for session %s", session_id)

    settings = get_settings()
    redis_client: Any = None
    pubsub: Any = None
    takeover_active = False

    try:
        import redis.asyncio as aioredis

        # Use a dedicated connection (not pooled) to avoid stale connections
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
        )
        await redis_client.ping()
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"screenshots:{session_id}")
        logger.info("Redis pub/sub connected for screenshots:%s", session_id)
    except Exception as exc:
        logger.warning("Redis not available for WebSocket screenshot streaming: %s", exc)
        pubsub = None
        redis_client = None

    async def forward_screenshots():
        """Read from Redis pub/sub and send to WebSocket."""
        if not pubsub:
            return
        try:
            while True:
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if msg and msg["type"] == "message":
                    data = json.loads(msg["data"])
                    # Translate to the format the frontend expects
                    await websocket.send_json({
                        "type": "screenshot",
                        "image": data.get("screenshot", ""),
                        "url": data.get("url", ""),
                    })
                else:
                    await asyncio.sleep(0.1)
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception:
            logger.debug("Screenshot forward error", exc_info=True)

    async def receive_messages():
        """Handle incoming WebSocket messages (chat/steering)."""
        nonlocal takeover_active

        async def _send_takeover_status(
            *,
            active: bool,
            available: bool,
            reason: str | None = None,
        ) -> None:
            page = get_active_page(session_id)
            await websocket.send_json({
                "type": "takeover_status",
                "active": active,
                "available": available,
                "reason": reason or "",
                "url": page.url if page else "",
            })

        async def _handle_takeover_input(data: dict[str, Any]) -> None:
            page = get_active_page(session_id)
            if page is None or page.is_closed():
                await _send_takeover_status(
                    active=False,
                    available=False,
                    reason="No live browser page is available for takeover.",
                )
                return

            input_type = str(data.get("input_type", ""))
            action = str(data.get("action", ""))
            await page.bring_to_front()

            if input_type == "mouse":
                x = float(data.get("x", 0))
                y = float(data.get("y", 0))
                button = str(data.get("button", "left"))
                if action == "move":
                    await page.mouse.move(x, y)
                elif action == "click":
                    await page.mouse.click(
                        x,
                        y,
                        button=button,
                        click_count=int(data.get("click_count", 1)),
                    )
                elif action == "down":
                    await page.mouse.move(x, y)
                    await page.mouse.down(button=button)
                elif action == "up":
                    await page.mouse.move(x, y)
                    await page.mouse.up(button=button)
                elif action == "wheel":
                    await page.mouse.wheel(
                        float(data.get("delta_x", 0)),
                        float(data.get("delta_y", 0)),
                    )
            elif input_type == "keyboard":
                if action == "press":
                    await page.keyboard.press(str(data.get("key", "")))
                elif action == "type":
                    await page.keyboard.type(str(data.get("text", "")))

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    data = json.loads(raw)
                    msg_type = data.get("type", "chat")
                    message = data.get("message", "")

                    if msg_type == "takeover":
                        action = str(data.get("action", ""))
                        page = get_active_page(session_id)
                        available = page is not None and not page.is_closed()
                        if action == "request":
                            takeover_active = available
                            await _send_takeover_status(
                                active=takeover_active,
                                available=available,
                                reason="" if available else "No active browser page is available right now.",
                            )
                        elif action == "release":
                            takeover_active = False
                            await _send_takeover_status(
                                active=False,
                                available=available,
                            )
                    elif msg_type == "takeover_input":
                        if not takeover_active:
                            await _send_takeover_status(
                                active=False,
                                available=get_active_page(session_id) is not None,
                                reason="Take control first before sending browser input.",
                            )
                            continue
                        await _handle_takeover_input(data)
                    elif msg_type == "chat" and message:
                        # Inject steering message into the graph
                        from backend.gateway.routes.sessions import _emit

                        await _emit(session_id, "status", {
                            "status": "steering",
                            "message": f"User: {message}",
                        })

                        # Also update graph state if available
                        try:
                            from fastapi import Request
                            # We can't access app.state from here directly,
                            # so publish a steering command via Redis
                            if redis_client:
                                await redis_client.publish(
                                    f"steer:{session_id}",
                                    json.dumps({"message": message}),
                                )
                        except Exception:
                            pass

                except json.JSONDecodeError:
                    pass
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception:
            logger.debug("WebSocket receive error", exc_info=True)

    # Run both tasks concurrently
    forward_task = asyncio.create_task(forward_screenshots())
    receive_task = asyncio.create_task(receive_messages())

    try:
        # Wait until either task finishes (client disconnects)
        done, pending = await asyncio.wait(
            [forward_task, receive_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
    except Exception:
        forward_task.cancel()
        receive_task.cancel()
    finally:
        if pubsub:
            await pubsub.unsubscribe(f"screenshots:{session_id}")
            await pubsub.close()
        if redis_client:
            await redis_client.close()
        logger.info("WebSocket disconnected for session %s", session_id)
