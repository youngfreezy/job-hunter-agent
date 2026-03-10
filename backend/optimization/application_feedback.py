# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Application feedback loop — learns ATS-specific strategies from outcomes.

Analyzes per-application results grouped by ATS type (Greenhouse, Lever,
Workday, etc.) to extract success/failure patterns. When 5+ attempts
accumulate for an ATS, generates a natural-language strategy tip that gets
injected into the Skyvern navigation goal and resume tailoring prompts.

This is the third self-improvement loop:
  1. Moltbook — community signals
  2. EvoAgentX — prompt evolution via TextGrad
  3. Application feedback — ATS-specific strategies from own outcomes  ← this
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from backend.shared.db import get_pool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_ATTEMPTS = 5  # Minimum attempts per ATS before generating strategy
_TABLE_ENSURED = False

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS ats_strategies (
    ats_type TEXT PRIMARY KEY,
    strategy_tip TEXT NOT NULL,
    success_rate FLOAT DEFAULT 0.0,
    total_attempts INT DEFAULT 0,
    top_errors JSONB,
    top_failure_steps JSONB,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
"""

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _ensure_table() -> None:
    global _TABLE_ENSURED
    if _TABLE_ENSURED:
        return
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(_CREATE_TABLE)
        conn.commit()
    _TABLE_ENSURED = True


def get_ats_tips(ats_type: str) -> Optional[str]:
    """Return the strategy tip for an ATS type, or None if not enough data."""
    if not ats_type or ats_type == "unknown":
        return None
    try:
        _ensure_table()
        pool = get_pool()
        with pool.connection() as conn:
            row = conn.execute(
                "SELECT strategy_tip FROM ats_strategies WHERE ats_type = %s",
                (ats_type.lower(),),
            ).fetchone()
        return row[0] if row else None
    except Exception:
        logger.warning("Failed to fetch ATS tips for %s", ats_type, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def analyze_ats_outcomes() -> Dict[str, Dict[str, Any]]:
    """Query application_results grouped by ATS type.

    Returns a dict keyed by ats_type with:
      - total, submitted, failed, skipped counts
      - success_rate (submitted / (submitted + failed))
      - top_errors: {error_category: count} top 3
      - top_failure_steps: {step: count} top 3
    """
    pool = get_pool()
    with pool.connection() as conn:
        rows = conn.execute("""
            SELECT
                LOWER(COALESCE(ats_type, 'unknown')) AS ats,
                status,
                error_category,
                failure_step,
                COUNT(*) AS cnt
            FROM application_results
            GROUP BY ats, status, error_category, failure_step
        """).fetchall()

    # Aggregate
    data: Dict[str, Dict[str, Any]] = {}
    for ats, status, error_cat, failure_step, cnt in rows:
        if ats not in data:
            data[ats] = {
                "total": 0, "submitted": 0, "failed": 0, "skipped": 0,
                "errors": {}, "failure_steps": {},
            }
        d = data[ats]
        d["total"] += cnt
        if status == "submitted":
            d["submitted"] += cnt
        elif status == "failed":
            d["failed"] += cnt
        else:
            d["skipped"] += cnt

        if error_cat and status == "failed":
            d["errors"][error_cat] = d["errors"].get(error_cat, 0) + cnt
        if failure_step and status == "failed":
            d["failure_steps"][failure_step] = d["failure_steps"].get(failure_step, 0) + cnt

    # Compute success rates and sort top errors/steps
    for ats, d in data.items():
        attempted = d["submitted"] + d["failed"]
        d["success_rate"] = d["submitted"] / attempted if attempted > 0 else 0.0
        d["top_errors"] = dict(sorted(d["errors"].items(), key=lambda x: -x[1])[:3])
        d["top_failure_steps"] = dict(sorted(d["failure_steps"].items(), key=lambda x: -x[1])[:3])

    return data


# ---------------------------------------------------------------------------
# Strategy generation
# ---------------------------------------------------------------------------


def _generate_strategy_with_llm(ats_type: str, stats: Dict[str, Any]) -> str:
    """Use Haiku to synthesize outcome data into a strategy tip."""
    try:
        import anthropic

        client = anthropic.Anthropic()
        prompt = (
            f"You are an expert at filling out job application forms on ATS platforms.\n\n"
            f"Here are our historical results for {ats_type.upper()} forms:\n"
            f"- Total attempts: {stats['total']}\n"
            f"- Submitted successfully: {stats['submitted']} ({stats['success_rate']:.0%})\n"
            f"- Failed: {stats['failed']}\n"
            f"- Top error categories: {json.dumps(stats['top_errors'])}\n"
            f"- Top failure steps: {json.dumps(stats['top_failure_steps'])}\n\n"
            f"Based on these patterns, write 2-3 concise sentences of practical guidance "
            f"for an AI browser agent filling out a {ats_type} application form. "
            f"Focus on avoiding the most common failure modes. "
            f"Be specific to {ats_type}'s known form patterns (multi-page, field types, etc). "
            f"Do NOT include any preamble — just the guidance."
        )

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    except Exception:
        logger.warning("LLM strategy generation failed for %s, using fallback", ats_type, exc_info=True)
        return _generate_strategy_fallback(ats_type, stats)


def _generate_strategy_fallback(ats_type: str, stats: Dict[str, Any]) -> str:
    """Rule-based fallback if LLM call fails."""
    parts = [f"{ats_type.capitalize()} forms: {stats['success_rate']:.0%} success rate."]

    top_error = next(iter(stats.get("top_errors", {})), None)
    if top_error:
        error_tips = {
            "form_fill_error": "Watch for required fields that may be hidden or need scrolling.",
            "timeout": "This ATS often has slow-loading pages. Wait for elements to appear.",
            "auth_required": "This ATS frequently requires account creation. Stop early if login walls appear.",
            "captcha": "CAPTCHA challenges are common. Be prepared for manual intervention.",
            "no_confirmation": "Confirmation pages may not load. Check for success indicators carefully.",
            "submit_failed": "The submit button may require scrolling into view or a specific click sequence.",
        }
        tip = error_tips.get(top_error, f"Most common blocker: {top_error}.")
        parts.append(tip)

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Refresh / update strategies
# ---------------------------------------------------------------------------


def refresh_all_strategies() -> int:
    """Re-analyze all ATS outcomes and update strategies.

    Returns the number of ATS types updated.
    """
    _ensure_table()
    outcomes = analyze_ats_outcomes()
    updated = 0

    pool = get_pool()
    for ats_type, stats in outcomes.items():
        if ats_type == "unknown":
            continue
        if stats["total"] < MIN_ATTEMPTS:
            logger.debug("Skipping %s: only %d attempts (need %d)", ats_type, stats["total"], MIN_ATTEMPTS)
            continue

        strategy_tip = _generate_strategy_with_llm(ats_type, stats)

        with pool.connection() as conn:
            conn.execute("""
                INSERT INTO ats_strategies (ats_type, strategy_tip, success_rate, total_attempts, top_errors, top_failure_steps, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (ats_type) DO UPDATE SET
                    strategy_tip = EXCLUDED.strategy_tip,
                    success_rate = EXCLUDED.success_rate,
                    total_attempts = EXCLUDED.total_attempts,
                    top_errors = EXCLUDED.top_errors,
                    top_failure_steps = EXCLUDED.top_failure_steps,
                    updated_at = NOW()
            """, (
                ats_type,
                strategy_tip,
                stats["success_rate"],
                stats["total"],
                json.dumps(stats["top_errors"]),
                json.dumps(stats["top_failure_steps"]),
            ))
            conn.commit()

        logger.info(
            "Updated ATS strategy for %s: %.0f%% success (%d attempts) — %s",
            ats_type, stats["success_rate"] * 100, stats["total"], strategy_tip[:80],
        )
        updated += 1

    return updated
