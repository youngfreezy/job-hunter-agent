# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Self-improvement feedback processing for Moltbook integration.

Correlates application performance metrics with community feedback
to produce strategy patches that improve the agent's decision-making.

Security invariants:
- All Moltbook content sanitized before any use
- 5+ consistent signals required before accepting any strategy change
- Human review flag when automated adjustments accumulate
- Never stores or exposes PII, credentials, or resume content
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.moltbook.sanitize import sanitize
from backend.moltbook.strategies import get_strategy_manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Performance tracking
# ---------------------------------------------------------------------------

# Topic categories we look for in Moltbook posts
_RELEVANT_TOPICS = {
    "job_boards", "scraping", "browser_automation", "auth_walls",
    "captcha", "ats", "greenhouse", "lever", "workday", "ashby",
    "linkedin", "indeed", "glassdoor", "ziprecruiter",
    "application", "form_fill", "resume", "cover_letter",
    "discovery", "rate_limit", "proxy", "skyvern",
    # Broader strategy signals from community feedback
    "filter", "expired", "date", "posting", "stale", "old listing",
    "success rate", "conversion", "timeout", "retry", "backfill",
    "apply", "submit", "blocker", "workaround",
}


@dataclass
class PerformanceMetrics:
    """Aggregated application performance metrics (anonymized)."""

    total_applications: int = 0
    successful_applications: int = 0
    failed_applications: int = 0

    # Per-board stats
    board_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    # Per-ATS-type stats
    ats_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    # Per-role-type stats (e.g. "engineering", "design", "product")
    role_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)

    # Blockers encountered
    blocker_counts: Dict[str, int] = field(default_factory=dict)

    last_updated: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_applications == 0:
            return 0.0
        return self.successful_applications / self.total_applications * 100

    @property
    def top_board(self) -> str:
        """Board with highest success rate (min 2 attempts)."""
        best_board = "unknown"
        best_rate = -1.0
        for board, stats in self.board_stats.items():
            total = stats.get("total", 0)
            if total < 2:
                continue
            rate = stats.get("success", 0) / total
            if rate > best_rate:
                best_rate = rate
                best_board = board
        return best_board

    @property
    def biggest_blocker(self) -> str:
        if not self.blocker_counts:
            return "none"
        return max(self.blocker_counts, key=self.blocker_counts.get)  # type: ignore


# Module-level metrics (reset each cron cycle — populated from DB)
_metrics = PerformanceMetrics()


def get_metrics() -> PerformanceMetrics:
    return _metrics


def reset_metrics() -> None:
    global _metrics
    _metrics = PerformanceMetrics()


# ---------------------------------------------------------------------------
# Metric recording (called from application result processing)
# ---------------------------------------------------------------------------


def record_application_result(
    *,
    board: str = "",
    ats_type: str = "",
    role_type: str = "",
    success: bool = False,
    blocker: str = "",
) -> None:
    """Record an application result for performance tracking.

    SECURITY: This function only stores anonymized aggregate counts.
    Never pass company names, job titles, or user data.
    """
    m = _metrics
    m.total_applications += 1
    if success:
        m.successful_applications += 1
    else:
        m.failed_applications += 1

    # Board stats
    if board:
        if board not in m.board_stats:
            m.board_stats[board] = {"total": 0, "success": 0, "failed": 0}
        m.board_stats[board]["total"] += 1
        m.board_stats[board]["success" if success else "failed"] += 1

    # ATS stats
    if ats_type:
        if ats_type not in m.ats_stats:
            m.ats_stats[ats_type] = {"total": 0, "success": 0, "failed": 0}
        m.ats_stats[ats_type]["total"] += 1
        m.ats_stats[ats_type]["success" if success else "failed"] += 1

    # Role stats
    if role_type:
        if role_type not in m.role_stats:
            m.role_stats[role_type] = {"total": 0, "success": 0, "failed": 0}
        m.role_stats[role_type]["total"] += 1
        m.role_stats[role_type]["success" if success else "failed"] += 1

    # Blockers
    if blocker:
        m.blocker_counts[blocker] = m.blocker_counts.get(blocker, 0) + 1

    m.last_updated = time.time()


# ---------------------------------------------------------------------------
# Feed analysis — extract actionable signals from Moltbook posts
# ---------------------------------------------------------------------------


def is_relevant_post(post: Dict[str, Any]) -> bool:
    """Check if a Moltbook post is relevant to our domain."""
    content = (post.get("content") or "").lower()
    return any(topic in content for topic in _RELEVANT_TOPICS)


def extract_signals(post: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract actionable signals from a relevant Moltbook post.

    Returns a list of signal dicts with:
    - patch_id: deterministic ID for dedup
    - category: strategy category
    - content: sanitized strategy text
    - source_post_id: the Moltbook post ID

    SECURITY: All content is sanitized before being returned.
    """
    raw_content = post.get("content", "")
    post_id = str(post.get("id", ""))

    # Sanitize first — use 2000 chars so signal keywords aren't truncated away
    content = sanitize(raw_content, max_length=2000, context=f"signal:{post_id}")
    if not content:
        return []

    content_lower = content.lower()
    signals: List[Dict[str, Any]] = []

    # Board-related signals
    for board in ["greenhouse", "lever", "workday", "ashby", "linkedin", "indeed", "glassdoor"]:
        if board in content_lower:
            patch_id = _make_patch_id(f"board:{board}", content)
            signals.append({
                "patch_id": patch_id,
                "category": "board_priority",
                "content": content,
                "source_post_id": post_id,
            })

    # ATS strategy signals
    for ats in ["greenhouse", "lever", "workday", "ashby"]:
        if ats in content_lower and any(
            kw in content_lower
            for kw in ["form", "fill", "submit", "strategy", "tip", "workaround"]
        ):
            patch_id = _make_patch_id(f"ats:{ats}", content)
            signals.append({
                "patch_id": patch_id,
                "category": "ats_strategy",
                "content": content,
                "source_post_id": post_id,
            })

    # Blocker signals
    blocker_keywords = ["captcha", "auth wall", "blocked", "rate limit", "proxy", "timeout"]
    for kw in blocker_keywords:
        if kw in content_lower:
            patch_id = _make_patch_id(f"blocker:{kw}", content)
            signals.append({
                "patch_id": patch_id,
                "category": "blocker_workaround",
                "content": content,
                "source_post_id": post_id,
            })

    # Filtering / quality signals (e.g. "filter by date", "exclude expired")
    filter_keywords = ["filter", "expired", "stale", "old listing", "date", "exclude", "skip"]
    if any(kw in content_lower for kw in filter_keywords):
        patch_id = _make_patch_id("quality_filter", content)
        signals.append({
            "patch_id": patch_id,
            "category": "quality_filter",
            "content": content,
            "source_post_id": post_id,
        })

    # General community tips
    tip_keywords = ["tip", "trick", "found that", "works better", "recommend", "try using"]
    if any(kw in content_lower for kw in tip_keywords) and not signals:
        patch_id = _make_patch_id("community_tip", content)
        signals.append({
            "patch_id": patch_id,
            "category": "community_tip",
            "content": content,
            "source_post_id": post_id,
        })

    return signals


def process_signal(signal: Dict[str, Any]) -> None:
    """Process a single signal — add it to the strategy manager.

    This respects the 5-signal threshold and max-20-patches cap.
    """
    mgr = get_strategy_manager()
    mgr.add_signal(
        patch_id=signal["patch_id"],
        category=signal["category"],
        content=signal["content"],
        source="moltbook_feed",
        source_post_id=signal.get("source_post_id", ""),
    )


def process_feed_posts(posts: List[Dict[str, Any]]) -> int:
    """Process a batch of Moltbook feed posts for strategy signals.

    Returns the number of signals processed.
    """
    total_signals = 0
    for post in posts:
        if not is_relevant_post(post):
            continue
        signals = extract_signals(post)
        for signal in signals:
            process_signal(signal)
            total_signals += 1

    if total_signals > 0:
        logger.info("Processed %d strategy signals from %d feed posts", total_signals, len(posts))

    return total_signals


# ---------------------------------------------------------------------------
# Performance-based strategy updates
# ---------------------------------------------------------------------------


def update_strategies_from_performance() -> None:
    """Adjust board priorities based on observed performance metrics.

    Only makes adjustments when we have sufficient data (5+ attempts per board).
    """
    mgr = get_strategy_manager()
    m = get_metrics()

    for board, stats in m.board_stats.items():
        total = stats.get("total", 0)
        if total < 5:
            continue

        success_rate = stats.get("success", 0) / total

        # Adjust priority: +0.05 if success > 60%, -0.05 if < 30%
        if success_rate > 0.6:
            mgr.update_board_priority(board, 0.05)
        elif success_rate < 0.3:
            mgr.update_board_priority(board, -0.05)

    # Record top blockers
    for blocker, count in m.blocker_counts.items():
        if count >= 3:
            mgr.add_blocker(blocker, f"Encountered {count} times in recent applications")

    m.last_updated = time.time()


# ---------------------------------------------------------------------------
# Anonymization for outbound posts
# ---------------------------------------------------------------------------


def generate_performance_summary() -> str:
    """Generate an anonymized performance summary for Moltbook posting.

    SECURITY: Never includes company names, job titles, user data, or PII.
    Only reports aggregate statistics.
    """
    m = get_metrics()

    if m.total_applications == 0:
        return "No applications tracked yet this cycle."

    lines = [
        f"JobHunter Agent stats: {m.total_applications} automated applications this week.",
        f"Success rate: {m.success_rate:.0f}% across all test runs.",
        f"Top performing board: {m.top_board}.",
    ]

    if m.biggest_blocker != "none":
        lines.append(f"Biggest blocker for the agent: {m.biggest_blocker}.")

    # Board breakdown (anonymized counts only)
    board_lines = []
    for board, stats in sorted(m.board_stats.items()):
        total = stats.get("total", 0)
        success = stats.get("success", 0)
        if total > 0:
            board_lines.append(f"  {board}: {success}/{total} successful")
    if board_lines:
        lines.append("Board breakdown:")
        lines.extend(board_lines)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_patch_id(prefix: str, content: str) -> str:
    """Create a deterministic patch ID from prefix + content hash."""
    content_hash = hashlib.sha256(content.encode()).hexdigest()[:12]
    return f"{prefix}:{content_hash}"
