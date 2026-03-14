# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Central registry of all store table-ensure functions.

Single source of truth for which tables need to be created on startup.
Adding a new store module? Add its ensure function here.
"""

from __future__ import annotations

import inspect
import logging
from typing import Callable, List, Tuple

logger = logging.getLogger(__name__)


def _get_all_ensure_functions() -> List[Tuple[str, Callable]]:
    """Import and return all store ensure functions.

    This is the ONE place to add new stores. If you forget,
    the table won't exist on startup and queries will fail.
    """
    from backend.browser.tools.apply_selectors import ensure_table as ensure_apply_selectors
    from backend.shared.agent_store import ensure_agent_tables
    from backend.shared.application_store import ensure_table as ensure_application
    from backend.shared.autopilot_store import ensure_autopilot_tables
    from backend.shared.billing_store import ensure_billing_tables
    from backend.shared.credential_store import ensure_table as ensure_credentials
    from backend.shared.screenshot_store import _ensure_table as ensure_screenshots
    from backend.shared.selector_memory import ensure_table as ensure_selectors
    from backend.shared.webhook_store import _ensure_webhook_tables
    from backend.moltbook.strategies import ensure_strategy_table

    return [
        ("selector_memory", ensure_selectors),
        ("apply_selectors", ensure_apply_selectors),
        ("application_store", ensure_application),
        ("billing_store", ensure_billing_tables),
        ("autopilot_store", ensure_autopilot_tables),
        ("agent_store", ensure_agent_tables),
        ("credential_store", ensure_credentials),
        ("webhook_store", _ensure_webhook_tables),
        ("screenshot_store", ensure_screenshots),
        ("moltbook_strategy", ensure_strategy_table),
    ]


async def ensure_all_tables() -> None:
    """Create all store tables. Called once on startup."""
    for name, fn in _get_all_ensure_functions():
        try:
            result = fn()
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.warning("%s table setup failed (non-fatal)", name, exc_info=True)
    logger.info("All store tables ensured")
