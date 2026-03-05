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
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    data = json.loads(raw)
                    msg_type = data.get("type", "chat")
                    message = data.get("message", "")

                    if msg_type == "chat" and message:
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
