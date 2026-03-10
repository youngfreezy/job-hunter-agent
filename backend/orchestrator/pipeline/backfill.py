# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Reusable backfill utilities for the LangGraph pipeline.

Provides a generic ``should_backfill`` predicate that any pipeline stage can
use to decide whether to loop back for more work.  The pattern compares a
current metric (e.g. submitted applications) against a target (e.g. max_jobs)
and respects a configurable round limit + stall detection.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Default maximum backfill rounds before giving up.
MAX_BACKFILL_ROUNDS = 3


def should_backfill(
    state: Dict[str, Any],
    current_count: int,
    target_count: int,
    rounds_key: str = "backfill_rounds",
    prev_count_key: str = "_prev_backfill_submitted",
    max_rounds: int = MAX_BACKFILL_ROUNDS,
) -> bool:
    """Generic backfill check -- reusable across pipeline stages.

    Parameters
    ----------
    state : dict
        Current pipeline state.
    current_count : int
        How many items have been successfully produced so far.
    target_count : int
        How many items the user requested.
    rounds_key : str
        State key that tracks how many backfill rounds have occurred.
    prev_count_key : str
        State key that tracks the count before the last backfill round
        (used for stall/no-progress detection).
    max_rounds : int
        Maximum number of backfill rounds allowed.

    Returns
    -------
    bool
        True if another backfill round should be attempted.
    """
    if current_count >= target_count:
        return False

    rounds = state.get(rounds_key, 0)
    if rounds >= max_rounds:
        logger.info(
            "Backfill: max rounds (%d) reached with %d/%d -- stopping",
            max_rounds, current_count, target_count,
        )
        return False

    # Stall detection: if the last round made zero progress, stop.
    if rounds > 0:
        prev = state.get(prev_count_key, 0)
        if current_count <= prev:
            logger.warning(
                "Backfill: no progress (prev=%d, current=%d) -- stopping",
                prev, current_count,
            )
            return False

    return True
