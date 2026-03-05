"""Shared event bus for emitting SSE events from agents.

Agents (career_coach, discovery, etc.) can emit progress events to the
frontend without coupling to the FastAPI route layer. The sessions route
registers an emit callback per session_id at pipeline start.
"""

from __future__ import annotations

import asyncio
from typing import Callable, Awaitable, Dict, Optional

# session_id -> async emit callback
_emitters: Dict[str, Callable[[str, str, dict], Awaitable[None]]] = {}


def register_emitter(
    session_id: str,
    emitter: Callable[[str, str, dict], Awaitable[None]],
) -> None:
    """Register an SSE emit callback for a session."""
    _emitters[session_id] = emitter


def unregister_emitter(session_id: str) -> None:
    """Remove the emitter when the pipeline finishes."""
    _emitters.pop(session_id, None)


async def emit_agent_event(
    session_id: str,
    event_type: str,
    data: dict,
) -> None:
    """Emit an SSE event from within an agent node.

    Safe to call even if no emitter is registered (silently no-ops).
    """
    emitter = _emitters.get(session_id)
    if emitter is not None:
        await emitter(session_id, event_type, data)
