"""Registry for the currently active Playwright page per session.

The application agent owns the real browser page. WebSocket takeover uses
this registry to forward operator input to that live page.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

_active_pages: Dict[str, Any] = {}


def register_active_page(session_id: str, page: Any) -> None:
    """Expose the current live page for takeover."""
    _active_pages[session_id] = page


def unregister_active_page(session_id: str, page: Any | None = None) -> None:
    """Clear the current page when the application page closes."""
    current = _active_pages.get(session_id)
    if page is not None and current is not page:
        return
    _active_pages.pop(session_id, None)


def get_active_page(session_id: str) -> Optional[Any]:
    """Return the live page for *session_id*, if one is registered."""
    return _active_pages.get(session_id)
