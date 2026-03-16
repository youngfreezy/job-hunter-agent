# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Paperclip REST API client for agent orchestration.

Thin wrapper around Paperclip's REST API for reporting agent heartbeats,
cost events, and issue management. Used by the scheduler to report
async agent activity (Moltbook, autopilot, cleanup, health checks)
to the Paperclip dashboard.

Architecture:
    ┌──────────────┐     heartbeat      ┌──────────────┐
    │  Backend     │ ──────────────────▶ │  Paperclip   │
    │  Scheduler   │                     │  Server      │
    │              │ ◀────────────────── │  (:3100)     │
    │  (cron jobs) │     agent info      │              │
    └──────────────┘                     └──────────────┘
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import httpx

from backend.shared.config import get_settings

logger = logging.getLogger(__name__)

# Agent registry — maps agent name to Paperclip agent ID + token
_AGENT_REGISTRY: Dict[str, Dict[str, str]] = {}


def configure_agents(agents: Dict[str, Dict[str, str]]) -> None:
    """Register Paperclip agent credentials.

    Args:
        agents: Mapping of agent name to {"id": ..., "token": ...}
    """
    _AGENT_REGISTRY.update(agents)
    logger.info("Paperclip: configured %d agents", len(agents))


def _base_url() -> str:
    return get_settings().PAPERCLIP_API_URL.rstrip("/")


def _headers(agent_name: str) -> Dict[str, str]:
    agent = _AGENT_REGISTRY.get(agent_name)
    if not agent:
        raise ValueError(f"Paperclip agent '{agent_name}' not configured")
    return {
        "Authorization": f"Bearer {agent['token']}",
        "Content-Type": "application/json",
    }


def _company_id() -> str:
    return get_settings().PAPERCLIP_COMPANY_ID


# ── Agent Info ──────────────────────────────────────────────────────

def get_agent_info(agent_name: str) -> Optional[Dict[str, Any]]:
    """Fetch agent's own info from Paperclip (GET /api/agents/me)."""
    try:
        resp = httpx.get(
            f"{_base_url()}/agents/me",
            headers=_headers(agent_name),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        logger.debug("Paperclip: failed to get agent info for %s", agent_name, exc_info=True)
        return None


# ── Cost Reporting ──────────────────────────────────────────────────

def report_cost(
    agent_name: str,
    cost_cents: int,
    token_count: int = 0,
    description: str = "",
    project_id: Optional[str] = None,
) -> bool:
    """Report a cost event to Paperclip for budget tracking.

    Returns True if reported successfully, False otherwise.
    Non-blocking — failures are logged but don't interrupt agent work.
    """
    agent = _AGENT_REGISTRY.get(agent_name)
    if not agent:
        return False

    payload: Dict[str, Any] = {
        "agentId": agent["id"],
        "costCents": cost_cents,
        "tokenCount": token_count,
        "description": description,
    }
    if project_id:
        payload["projectId"] = project_id

    try:
        resp = httpx.post(
            f"{_base_url()}/companies/{_company_id()}/cost-events",
            headers=_headers(agent_name),
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception:
        logger.debug("Paperclip: failed to report cost for %s", agent_name, exc_info=True)
        return False


# ── Issue Management ────────────────────────────────────────────────

def create_issue(
    agent_name: str,
    title: str,
    description: str = "",
    priority: str = "medium",
) -> Optional[Dict[str, Any]]:
    """Create a new issue/ticket in Paperclip."""
    try:
        resp = httpx.post(
            f"{_base_url()}/companies/{_company_id()}/issues",
            headers=_headers(agent_name),
            json={
                "title": title,
                "description": description,
                "priority": priority,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        logger.debug("Paperclip: failed to create issue", exc_info=True)
        return None


def update_issue(
    agent_name: str,
    issue_id: str,
    status: Optional[str] = None,
    comment: Optional[str] = None,
) -> bool:
    """Update an issue status or add a comment."""
    payload: Dict[str, Any] = {}
    if status:
        payload["status"] = status
    if comment:
        payload["comment"] = comment

    try:
        resp = httpx.patch(
            f"{_base_url()}/issues/{issue_id}",
            headers=_headers(agent_name),
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception:
        logger.debug("Paperclip: failed to update issue %s", issue_id, exc_info=True)
        return False


# ── Activity Reporting ──────────────────────────────────────────────

def report_heartbeat(
    agent_name: str,
    status: str = "completed",
    summary: str = "",
    duration_seconds: float = 0,
    error: Optional[str] = None,
) -> bool:
    """Report agent heartbeat completion to Paperclip via activity log.

    Creates an issue that captures the heartbeat result, then immediately
    marks it done. This provides a clean audit trail in Paperclip's
    activity feed.
    """
    desc = summary
    if error:
        desc = f"ERROR: {error}\n\n{summary}"
    if duration_seconds:
        desc += f"\n\nDuration: {duration_seconds:.1f}s"

    title = f"[{agent_name}] {'✓' if status == 'completed' else '✗'} {summary[:80]}"

    issue = create_issue(agent_name, title=title, description=desc, priority="low")
    if issue:
        update_issue(agent_name, issue["id"], status="done")
        return True
    return False
