# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Persistent storage for webhook subscriptions and delivery logs."""

from __future__ import annotations

import logging
import secrets
import uuid
from typing import Any, Dict, List, Optional

from backend.shared.db import get_connection

logger = logging.getLogger(__name__)

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS webhooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    url TEXT NOT NULL,
    secret TEXT NOT NULL,
    events TEXT[] NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_webhooks_user ON webhooks(user_id);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    webhook_id UUID REFERENCES webhooks(id) ON DELETE CASCADE NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    response_status INTEGER,
    response_body TEXT,
    delivered_at TIMESTAMPTZ DEFAULT NOW(),
    success BOOLEAN DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_webhook ON webhook_deliveries(webhook_id);

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    key_hash TEXT NOT NULL,
    key_prefix TEXT NOT NULL,
    name TEXT NOT NULL,
    scopes TEXT[] DEFAULT '{agents:read,agents:write,webhooks:manage}',
    is_active BOOLEAN DEFAULT TRUE,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
"""


def _ensure_webhook_tables() -> None:
    """Create webhook + api_key tables if they don't exist."""
    try:
        with get_connection() as conn:
            conn.execute(_CREATE_TABLES)
            conn.commit()
            logger.info("Webhook/API key tables ensured")
    except Exception:
        logger.exception("Failed to create webhook/API key tables")


VALID_EVENTS = {
    "agent.started",
    "agent.stage_changed",
    "agent.completed",
    "agent.failed",
}


def create_webhook(
    user_id: str,
    url: str,
    events: List[str],
) -> Dict[str, Any]:
    """Create a new webhook subscription. Auto-generates HMAC signing secret."""
    # Validate events
    invalid = set(events) - VALID_EVENTS
    if invalid:
        raise ValueError(f"Invalid events: {invalid}. Valid: {VALID_EVENTS}")

    webhook_id = str(uuid.uuid4())
    secret = f"whsec_{secrets.token_urlsafe(32)}"

    with get_connection() as conn:
        conn.execute(
            """INSERT INTO webhooks (id, user_id, url, secret, events)
               VALUES (%s, %s, %s, %s, %s)""",
            (webhook_id, user_id, url, secret, events),
        )
        conn.commit()

    return {
        "id": webhook_id,
        "url": url,
        "secret": secret,
        "events": events,
        "is_active": True,
    }


def list_webhooks(user_id: str) -> List[Dict[str, Any]]:
    """List all webhooks for a user."""
    with get_connection() as conn:
        cur = conn.execute(
            """SELECT id, url, secret, events, is_active, created_at, updated_at
               FROM webhooks
               WHERE user_id = %s
               ORDER BY created_at DESC""",
            (user_id,),
        )
        return [
            {
                "id": str(row[0]),
                "url": row[1],
                "secret": row[2],
                "events": row[3],
                "is_active": row[4],
                "created_at": row[5].isoformat() if row[5] else None,
                "updated_at": row[6].isoformat() if row[6] else None,
            }
            for row in cur.fetchall()
        ]


def update_webhook(
    webhook_id: str,
    user_id: str,
    url: Optional[str] = None,
    events: Optional[List[str]] = None,
    is_active: Optional[bool] = None,
) -> Optional[Dict[str, Any]]:
    """Update a webhook subscription. Returns updated webhook or None if not found."""
    if events:
        invalid = set(events) - VALID_EVENTS
        if invalid:
            raise ValueError(f"Invalid events: {invalid}")

    updates = []
    params: list = []
    if url is not None:
        updates.append("url = %s")
        params.append(url)
    if events is not None:
        updates.append("events = %s")
        params.append(events)
    if is_active is not None:
        updates.append("is_active = %s")
        params.append(is_active)
    if not updates:
        return None

    updates.append("updated_at = NOW()")
    params.extend([webhook_id, user_id])

    with get_connection() as conn:
        cur = conn.execute(
            f"UPDATE webhooks SET {', '.join(updates)} WHERE id = %s AND user_id = %s RETURNING id, url, events, is_active",
            params,
        )
        row = cur.fetchone()
        conn.commit()
        if not row:
            return None
        return {
            "id": str(row[0]),
            "url": row[1],
            "events": row[2],
            "is_active": row[3],
        }


def delete_webhook(webhook_id: str, user_id: str) -> bool:
    """Delete a webhook. Returns True if found and deleted."""
    with get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM webhooks WHERE id = %s AND user_id = %s RETURNING id",
            (webhook_id, user_id),
        )
        deleted = cur.fetchone() is not None
        conn.commit()
        return deleted


def get_webhooks_for_event(user_id: str, event_type: str) -> List[Dict[str, Any]]:
    """Get all active webhooks for a user that subscribe to a given event."""
    with get_connection() as conn:
        cur = conn.execute(
            """SELECT id, url, secret
               FROM webhooks
               WHERE user_id = %s AND is_active = TRUE AND %s = ANY(events)""",
            (user_id, event_type),
        )
        return [
            {"id": str(row[0]), "url": row[1], "secret": row[2]}
            for row in cur.fetchall()
        ]


def log_delivery(
    webhook_id: str,
    event_type: str,
    payload: dict,
    response_status: Optional[int] = None,
    response_body: Optional[str] = None,
    success: bool = False,
) -> None:
    """Log a webhook delivery attempt."""
    with get_connection() as conn:
        import json
        conn.execute(
            """INSERT INTO webhook_deliveries
               (webhook_id, event_type, payload, response_status, response_body, success)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (webhook_id, event_type, json.dumps(payload), response_status, response_body, success),
        )
        conn.commit()


def list_deliveries(webhook_id: str, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """List recent delivery logs for a webhook (with ownership check)."""
    with get_connection() as conn:
        cur = conn.execute(
            """SELECT wd.id, wd.event_type, wd.payload, wd.response_status,
                      wd.response_body, wd.success, wd.delivered_at
               FROM webhook_deliveries wd
               JOIN webhooks w ON w.id = wd.webhook_id
               WHERE wd.webhook_id = %s AND w.user_id = %s
               ORDER BY wd.delivered_at DESC
               LIMIT %s""",
            (webhook_id, user_id, limit),
        )
        return [
            {
                "id": str(row[0]),
                "event_type": row[1],
                "payload": row[2],
                "response_status": row[3],
                "response_body": row[4],
                "success": row[5],
                "delivered_at": row[6].isoformat() if row[6] else None,
            }
            for row in cur.fetchall()
        ]
