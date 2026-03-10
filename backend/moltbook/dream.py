# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Dream cycle -- sleep-time compute / memory consolidation for the Moltbook loop.

Periodically (every ~5 cron cycles) the agent enters a "dream" state where it:
  1. Gathers recent performance metrics, strategy patches, board priorities, community signals
  2. Reflects on patterns via LLM call
  3. Consolidates insights into compressed, durable learnings
  4. Prunes strategy patches that dreams identify as ineffective
  5. Auto-adjusts board priority weights based on dream conclusions (within bounds)

Dreams are deeper reflection, not reactive signal processing.

SECURITY:
- All LLM dream outputs are sanitized before storage
- Dreams cannot override the 5+ signal threshold for patches
- Dream insights are read-only context -- they inform but don't directly modify code/config
- Cap of 10 dream entries
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List

from backend.moltbook.sanitize import sanitize
from backend.moltbook.strategies import StrategyManager, get_strategy_manager

logger = logging.getLogger(__name__)

MAX_DREAM_LOGS = 10

# Board priority adjustment bounds from dream insights
_DREAM_PRIORITY_DELTA_MAX = 0.1


async def run_dream_cycle(
    strategies: StrategyManager | None = None,
) -> None:
    """Execute a dream cycle -- deep reflection on recent performance.

    Gathers performance metrics, strategy patches, board priorities,
    and community signals; calls an LLM for reflection; sanitizes output;
    stores consolidated insights; and prunes ineffective strategy patches.
    """
    mgr = strategies or get_strategy_manager()
    state = mgr.get_state()

    # Gather context for reflection
    context_parts = []

    # Board priorities
    sorted_boards = sorted(state.board_priorities.items(), key=lambda x: x[1], reverse=True)
    if sorted_boards:
        context_parts.append("Board priorities:")
        for board, score in sorted_boards:
            context_parts.append(f"  - {board}: {score:.2f}")

    # ATS strategies
    if state.ats_strategies:
        context_parts.append("\nATS strategies:")
        for ats, strategy in state.ats_strategies.items():
            context_parts.append(f"  - {ats}: {strategy[:100]}")

    # Accepted patches
    accepted = mgr.get_accepted_patches()
    if accepted:
        context_parts.append(f"\nAccepted strategy patches ({len(accepted)}):")
        for patch in accepted:
            context_parts.append(
                f"  - [{patch.category}] {patch.content[:80]} (signals={patch.signal_count})"
            )

    # Known blockers
    if state.known_blockers:
        context_parts.append("\nKnown blockers:")
        for key, desc in state.known_blockers.items():
            context_parts.append(f"  - {key}: {desc[:80]}")

    # Performance metrics from the feedback loop
    try:
        from backend.moltbook.feedback_loop import get_metrics
        metrics = get_metrics()
        if metrics.total_applications > 0:
            context_parts.append(f"\nPerformance metrics:")
            context_parts.append(f"  - Total applications: {metrics.total_applications}")
            context_parts.append(f"  - Success rate: {metrics.success_rate:.0f}%")
            context_parts.append(f"  - Top board: {metrics.top_board}")
            context_parts.append(f"  - Biggest blocker: {metrics.biggest_blocker}")

            for board, stats in metrics.board_stats.items():
                total = stats.get("total", 0)
                success = stats.get("success", 0)
                if total > 0:
                    context_parts.append(f"  - {board}: {success}/{total} ({success/total*100:.0f}%)")
    except Exception as exc:
        logger.debug("Failed to load performance metrics for dream: %s", exc)

    # Previous dream insights for continuity
    prev_insights = get_dream_insights(mgr)
    if prev_insights:
        context_parts.append("\nPrevious dream insights:")
        for i, ins in enumerate(prev_insights):
            context_parts.append(f"  {i + 1}. {ins}")

    if not context_parts:
        logger.info("[dream] No context to reflect on -- skipping dream cycle")
        return

    reflection_prompt = (
        "Review this job application agent's recent performance: success rates, "
        "board effectiveness, community suggestions, and current strategies. "
        "What's working? What's failing? What should change? "
        "Compress into 3-5 strategic insights.\n\n"
        + "\n".join(context_parts)
        + "\n\nRespond with ONLY a JSON array of 3-5 insight strings. Example:\n"
        '["insight 1", "insight 2", "insight 3"]\n\n'
        "Do not include any text outside the JSON array."
    )

    try:
        logger.info("[dream] Starting dream cycle -- reflecting on strategy state...")

        insights = await _call_llm_for_reflection(reflection_prompt)

        if not insights:
            logger.info("[dream] No insights returned from LLM -- skipping")
            return

        # Sanitize each insight
        clean_insights = []
        for insight in insights[:5]:
            if isinstance(insight, str):
                clean = sanitize(insight, max_length=300, context="dream_insight")
                if clean:
                    clean_insights.append(clean)

        if not clean_insights:
            logger.warning("[dream] All insights empty after sanitization -- skipping")
            return

        # Store dream entry in strategies
        _store_dream(mgr, clean_insights)

        # Prune ineffective strategy patches based on dream insights
        _prune_ineffective_patches(mgr, clean_insights)

        # Auto-adjust board priorities based on dream conclusions
        _adjust_board_priorities(mgr, clean_insights)

        logger.info("[dream] Dream cycle complete -- stored %d insights", len(clean_insights))

    except Exception as e:
        logger.error("[dream] Dream cycle failed: %s", e)


async def _call_llm_for_reflection(prompt: str) -> List[str]:
    """Call an LLM for dream reflection.

    Uses the same ChatAnthropic pattern as the rest of the JobHunter backend.
    """
    try:
        from langchain_anthropic import ChatAnthropic
        from langchain_core.messages import HumanMessage, SystemMessage

        llm = ChatAnthropic(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            temperature=0.7,
        )

        messages = [
            SystemMessage(content=(
                "You are a reflective meta-analyst for a job application automation agent. "
                "Your job is to find patterns in application performance, board effectiveness, "
                "and community feedback, then compress your analysis into concise, actionable "
                "strategic insights. Be specific and evidence-based. "
                "Output only a JSON array of strings."
            )),
            HumanMessage(content=prompt),
        ]

        response = await llm.ainvoke(messages)
        raw_text = response.content if isinstance(response.content, str) else str(response.content)

        json_str = raw_text.strip()
        if json_str.startswith("```"):
            json_str = json_str.split("\n", 1)[1] if "\n" in json_str else json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            json_str = json_str.strip()

        result = json.loads(json_str)
        if isinstance(result, list):
            return [str(item) for item in result if isinstance(item, str)]

        logger.warning("[dream] LLM did not return a JSON array")
        return []

    except ImportError:
        logger.warning("[dream] langchain_anthropic not available -- skipping LLM call")
        return []
    except Exception as e:
        logger.error("[dream] LLM reflection call failed: %s", e)
        return []


def _store_dream(mgr: StrategyManager, insights: List[str]) -> None:
    """Store a dream entry in the strategy state."""
    state = mgr.get_state()

    if not hasattr(state, "dream_log"):
        # Initialize dream_log on the state dict level
        pass

    dream_entry = {
        "id": f"dream_{int(time.time())}",
        "insights": insights,
        "created_at": time.time(),
    }

    # Access raw state dict for dream_log storage
    raw_state = state.to_dict()
    dream_log = raw_state.get("dream_log", [])
    dream_log.append(dream_entry)

    # Cap at MAX_DREAM_LOGS
    while len(dream_log) > MAX_DREAM_LOGS:
        removed = dream_log.pop(0)
        logger.info("[dream] Rotated out oldest dream entry: %s", removed.get("id"))

    # Save back via the manager's internal state
    state_dict = state.to_dict()
    state_dict["dream_log"] = dream_log
    mgr._state = type(state).from_dict(state_dict)
    mgr._save()


def get_dream_insights(mgr: StrategyManager | None = None) -> List[str]:
    """Get the latest dream insights for injection into prompts.

    Returns an empty list if no dreams exist.
    """
    try:
        manager = mgr or get_strategy_manager()
        state = manager.get_state()
        state_dict = state.to_dict()
        dream_log = state_dict.get("dream_log", [])
        if not dream_log:
            return []
        latest = dream_log[-1]
        return latest.get("insights", [])
    except Exception as e:
        logger.debug("[dream] Failed to load dream insights: %s", e)
        return []


def _prune_ineffective_patches(mgr: StrategyManager, insights: List[str]) -> None:
    """Prune strategy patches that dream insights identify as ineffective.

    Only prunes patches that are already accepted (have 5+ signals).
    Dreams provide evidence-based reasoning; patches matching "ineffective",
    "not working", "stop", "remove", or "drop" signals get pruned.
    """
    insight_text = " ".join(insights).lower()
    state = mgr.get_state()

    # Check if any insights explicitly flag specific categories as ineffective
    ineffective_signals = [
        "ineffective", "not working", "stop using", "remove", "drop",
        "counterproductive", "harmful", "negative impact",
    ]

    if not any(signal in insight_text for signal in ineffective_signals):
        return

    original_count = len(state.patches)
    state.patches = [
        p for p in state.patches
        if not (
            p.accepted
            and any(
                signal in insight_text and p.category.lower() in insight_text
                for signal in ineffective_signals
            )
        )
    ]

    pruned = original_count - len(state.patches)
    if pruned > 0:
        logger.info("[dream] Pruned %d ineffective strategy patches", pruned)
        mgr._save()


def _adjust_board_priorities(mgr: StrategyManager, insights: List[str]) -> None:
    """Auto-adjust board priority weights based on dream conclusions.

    Adjustments are bounded by _DREAM_PRIORITY_DELTA_MAX to prevent wild swings.
    """
    insight_text = " ".join(insights).lower()
    state = mgr.get_state()

    # Look for board-specific signals in the insights
    boards = list(state.board_priorities.keys())
    adjustments_made = False

    for board in boards:
        board_lower = board.lower()
        if board_lower not in insight_text:
            continue

        # Check for positive signals
        positive_signals = ["performing well", "high success", "prioritize", "increase priority", "effective"]
        negative_signals = ["underperforming", "low success", "deprioritize", "decrease priority", "struggling"]

        delta = 0.0
        for signal in positive_signals:
            if signal in insight_text:
                # Check if this signal is near the board name (within ~100 chars)
                idx_signal = insight_text.find(signal)
                idx_board = insight_text.find(board_lower)
                if abs(idx_signal - idx_board) < 100:
                    delta = _DREAM_PRIORITY_DELTA_MAX
                    break

        if delta == 0.0:
            for signal in negative_signals:
                if signal in insight_text:
                    idx_signal = insight_text.find(signal)
                    idx_board = insight_text.find(board_lower)
                    if abs(idx_signal - idx_board) < 100:
                        delta = -_DREAM_PRIORITY_DELTA_MAX
                        break

        if delta != 0.0:
            current = state.board_priorities.get(board, 0.5)
            new_val = max(0.0, min(1.0, current + delta))
            state.board_priorities[board] = new_val
            adjustments_made = True
            logger.info(
                "[dream] Board priority %s: %.2f -> %.2f (dream-adjusted, delta=%.2f)",
                board, current, new_val, delta,
            )

    if adjustments_made:
        mgr._save()
