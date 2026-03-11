# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Developer platform REST API — API keys, webhooks, delivery logs."""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.gateway.deps import get_current_user
from backend.shared.api_key_store import generate_api_key, list_api_keys, revoke_api_key
from backend.shared.webhook_store import (
    VALID_EVENTS,
    create_webhook,
    delete_webhook,
    list_deliveries,
    list_webhooks,
    update_webhook,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/developer", tags=["developer"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CreateApiKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class CreateWebhookRequest(BaseModel):
    url: str = Field(..., min_length=10, max_length=2048)
    events: List[str] = Field(..., min_length=1)


class UpdateWebhookRequest(BaseModel):
    url: Optional[str] = Field(None, min_length=10, max_length=2048)
    events: Optional[List[str]] = None
    is_active: Optional[bool] = None


# ---------------------------------------------------------------------------
# API Key endpoints
# ---------------------------------------------------------------------------

@router.post("/api-keys")
async def create_api_key(body: CreateApiKeyRequest, request: Request):
    """Generate a new API key. The raw key is returned ONCE."""
    user = get_current_user(request)
    result = generate_api_key(user["id"], body.name)
    return {"api_key": result}


@router.get("/api-keys")
async def get_api_keys(request: Request):
    """List all API keys (prefix only, never the full key)."""
    user = get_current_user(request)
    keys = list_api_keys(user["id"])
    return {"api_keys": keys}


@router.delete("/api-keys/{key_id}")
async def delete_api_key(key_id: str, request: Request):
    """Revoke an API key."""
    user = get_current_user(request)
    revoked = revoke_api_key(key_id, user["id"])
    if not revoked:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"status": "revoked"}


# ---------------------------------------------------------------------------
# Webhook endpoints
# ---------------------------------------------------------------------------

@router.post("/webhooks")
async def create_webhook_endpoint(body: CreateWebhookRequest, request: Request):
    """Create a new webhook subscription."""
    user = get_current_user(request)
    try:
        result = create_webhook(user["id"], body.url, body.events)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"webhook": result}


@router.get("/webhooks")
async def get_webhooks(request: Request):
    """List all webhooks for the authenticated user."""
    user = get_current_user(request)
    webhooks = list_webhooks(user["id"])
    return {"webhooks": webhooks}


@router.put("/webhooks/{webhook_id}")
async def update_webhook_endpoint(
    webhook_id: str, body: UpdateWebhookRequest, request: Request
):
    """Update a webhook subscription."""
    user = get_current_user(request)
    try:
        result = update_webhook(
            webhook_id, user["id"],
            url=body.url, events=body.events, is_active=body.is_active,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"webhook": result}


@router.delete("/webhooks/{webhook_id}")
async def delete_webhook_endpoint(webhook_id: str, request: Request):
    """Delete a webhook subscription."""
    user = get_current_user(request)
    deleted = delete_webhook(webhook_id, user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"status": "deleted"}


@router.get("/webhooks/{webhook_id}/deliveries")
async def get_deliveries(webhook_id: str, request: Request, limit: int = 20):
    """List recent delivery logs for a webhook."""
    user = get_current_user(request)
    deliveries = list_deliveries(webhook_id, user["id"], limit=min(limit, 50))
    return {"deliveries": deliveries}


@router.get("/events")
async def list_event_types():
    """List all available webhook event types. Public."""
    return {"events": sorted(VALID_EVENTS)}
