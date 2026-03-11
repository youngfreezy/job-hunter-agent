# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Agent marketplace REST API.

Browse agents, view details, submit reviews.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.gateway.deps import get_current_user
from backend.shared.agent_store import (
    get_agent_by_slug,
    list_published_agents,
    list_reviews,
    record_usage,
    submit_review,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ReviewRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    review_text: Optional[str] = Field(None, max_length=2000)
    session_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/agents")
async def list_agents(category: Optional[str] = None):
    """List all published agents. Public — no auth required."""
    agents = list_published_agents(category=category)
    return {"agents": agents}


@router.get("/agents/{slug}")
async def get_agent(slug: str):
    """Get a single agent with its reviews. Public — no auth required."""
    agent = get_agent_by_slug(slug)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    reviews = list_reviews(slug, limit=10)
    return {"agent": agent, "reviews": reviews}


@router.post("/agents/{slug}/use")
async def use_agent(slug: str, request: Request):
    """Record an agent usage event. Returns the agent's frontend path for redirect."""
    user = get_current_user(request)
    agent = get_agent_by_slug(slug)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    usage_id = record_usage(slug, user["id"])
    return {
        "usage_id": usage_id,
        "frontend_path": agent["frontend_path"],
    }


@router.post("/agents/{slug}/review")
async def post_review(slug: str, body: ReviewRequest, request: Request):
    """Submit or update a review for an agent. Authenticated."""
    user = get_current_user(request)
    result = submit_review(
        agent_slug=slug,
        user_id=user["id"],
        rating=body.rating,
        review_text=body.review_text,
        session_id=body.session_id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"review": result}


@router.get("/agents/{slug}/reviews")
async def get_reviews(slug: str, limit: int = 20, offset: int = 0):
    """List reviews for an agent. Public."""
    reviews = list_reviews(slug, limit=min(limit, 50), offset=offset)
    return {"reviews": reviews}
