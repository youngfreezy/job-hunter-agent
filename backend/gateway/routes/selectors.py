# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Selector health-check API -- validates stored CSS selectors against live pages.

Covers both discovery selectors (board_selectors) and apply selectors
(apply_selectors). Uses the shared health-check runner.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from backend.gateway.deps import get_current_user
from backend.shared.model_access import is_server_model_owner

from backend.browser.tools.apply_selectors import (
    get_all_for_platform,
    get_all_selectors as get_all_apply_selectors,
)
from backend.shared.selector_memory import (
    get_all_for_board,
    get_all_selectors as get_all_discovery_selectors,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/selectors", tags=["selectors"])


def _require_selector_owner(request: Request) -> None:
    user = get_current_user(request)
    if not is_server_model_owner(str(user["id"])):
        raise HTTPException(status_code=403, detail="Selector maintenance is restricted to the service owner.")


@router.get("/status")
async def selector_status(request: Request, platform: Optional[str] = None):
    """Return current selector health for all or a specific platform.

    Returns both discovery and apply selectors with health info.
    """
    _require_selector_owner(request)
    if platform:
        discovery = get_all_for_board(platform)
        apply = get_all_for_platform(platform)
    else:
        discovery = get_all_discovery_selectors()
        apply = get_all_apply_selectors()

    return {
        "discovery": {"selectors": discovery, "count": len(discovery)},
        "apply": {"selectors": apply, "count": len(apply)},
    }


@router.post("/health-check")
async def trigger_health_check(request: Request, platform: Optional[str] = None):
    """Run selector validation against live pages.

    Checks both discovery and apply selectors. Records pass/fail per selector.
    """
    _require_selector_owner(request)
    from backend.shared.selector_health import run_selector_health_check

    results = await run_selector_health_check(platform=platform)
    return results
