# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Async webhook dispatcher — fire-and-forget delivery with HMAC signing.

Delivers webhook payloads to subscriber URLs with:
- HMAC-SHA256 signature in X-Webhook-Signature header
- 3 retries with exponential backoff
- Delivery logging for debugging
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict

import httpx

from backend.shared.webhook_store import get_webhooks_for_event, log_delivery

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_TIMEOUT = 10.0  # seconds


def _sign_payload(payload: str, secret: str) -> str:
    """Create HMAC-SHA256 signature of the payload."""
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


async def _deliver_single(
    webhook: Dict[str, Any],
    event_type: str,
    payload: dict,
) -> None:
    """Deliver a webhook with retries."""
    body = json.dumps({
        "event": event_type,
        "timestamp": time.time(),
        "data": payload,
    })
    signature = _sign_payload(body, webhook["secret"])
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": signature,
        "X-Webhook-Event": event_type,
    }

    last_status = None
    last_body = None
    success = False

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await client.post(webhook["url"], content=body, headers=headers)
                last_status = resp.status_code
                last_body = resp.text[:500]  # Truncate for storage
                if 200 <= resp.status_code < 300:
                    success = True
                    break
            except Exception as exc:
                last_body = str(exc)[:500]
                logger.debug(
                    "Webhook delivery attempt %d failed for %s: %s",
                    attempt + 1, webhook["url"], exc,
                )

            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)  # 1s, 2s backoff

    log_delivery(
        webhook_id=webhook["id"],
        event_type=event_type,
        payload=payload,
        response_status=last_status,
        response_body=last_body,
        success=success,
    )

    if not success:
        logger.warning(
            "Webhook delivery failed after %d retries: %s (status=%s)",
            _MAX_RETRIES, webhook["url"], last_status,
        )


async def dispatch_agent_event(
    user_id: str,
    event_type: str,
    payload: dict,
) -> None:
    """Fire webhooks for a user's agent event. Non-blocking (fire-and-forget).

    Call this after SSE broadcast in agent route _emit_* functions.
    """
    try:
        webhooks = get_webhooks_for_event(user_id, event_type)
        if not webhooks:
            return
        for wh in webhooks:
            asyncio.create_task(_deliver_single(wh, event_type, payload))
    except Exception:
        logger.debug("Failed to dispatch webhooks for user %s", user_id, exc_info=True)
