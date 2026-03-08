# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""In-process async signalling for pre-login HITL flow.

The application agent awaits a per-session ``asyncio.Event`` after opening
a job-board login page.  The gateway sets the event when the user confirms
they have logged in via the UI.
"""

from __future__ import annotations

import asyncio
from typing import Dict

# Session-scoped login events (in-memory, same process)
_login_events: Dict[str, asyncio.Event] = {}


def get_login_event(session_id: str) -> asyncio.Event:
    if session_id not in _login_events:
        _login_events[session_id] = asyncio.Event()
    return _login_events[session_id]


async def wait_for_login(session_id: str, timeout: float = 300.0) -> None:
    """Block until the user signals they have logged in (or timeout)."""
    event = get_login_event(session_id)
    event.clear()
    await asyncio.wait_for(event.wait(), timeout=timeout)


def signal_login_complete(session_id: str) -> None:
    """Called by the gateway when the user clicks 'I've logged in'."""
    event = get_login_event(session_id)
    event.set()


def cleanup(session_id: str) -> None:
    """Remove the event for a finished session."""
    _login_events.pop(session_id, None)
