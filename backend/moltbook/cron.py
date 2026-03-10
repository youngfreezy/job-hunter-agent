# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Moltbook self-improvement cron loop.

Runs every 30 minutes (via the shared scheduler or standalone):
1. Heartbeat check
2. Post anonymized performance updates
3. Share interesting findings
4. Scan feed for relevant posts & extract signals
5. Comment helpfully on relevant posts
6. Analyze engagement on past posts
7. Update strategy based on community + performance data

Runnable as:
    python -m backend.moltbook.cron          (standalone)
    schedule_seconds("moltbook", run, 1800)  (FastAPI background)

SECURITY: All Moltbook content is sanitized. Never posts PII, credentials,
resume content, or company names from active applications.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List

from backend.moltbook.client import MoltbookClient, get_rate_limiter
from backend.moltbook.feedback_loop import (
    extract_signals,
    generate_performance_summary,
    get_metrics,
    is_relevant_post,
    process_feed_posts,
    record_application_result,
    reset_metrics,
    update_strategies_from_performance,
)
from backend.moltbook.sanitize import sanitize, sanitize_for_posting
from backend.moltbook.strategies import get_strategy_manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CRON_INTERVAL_SECONDS = 30 * 60  # 30 minutes

# Dream cycle interval (every Nth cron cycle)
DREAM_CYCLE_INTERVAL = 5

# Max comments per cron cycle (be a good citizen)
MAX_COMMENTS_PER_CYCLE = 5

# Track our own post IDs to check engagement later
_our_post_ids: List[str] = []
_MAX_TRACKED_POSTS = 50

# Cycle counter for dream triggering
_cycle_count: int = 0


# ---------------------------------------------------------------------------
# Performance data loader (reads from Postgres, anonymized)
# ---------------------------------------------------------------------------


async def _load_performance_from_db() -> None:
    """Load recent application results from Postgres into metrics.

    SECURITY: Only loads aggregate counts. No company names, job titles,
    or user data leave the DB boundary.
    """
    try:
        from backend.shared.db import get_connection

        reset_metrics()

        with get_connection() as conn:
            # Aggregate stats from last 7 days
            rows = conn.execute(
                """
                SELECT
                    job_board,
                    ats_type,
                    status,
                    error_category,
                    COUNT(*) as cnt
                FROM application_results
                WHERE created_at > NOW() - INTERVAL '7 days'
                GROUP BY job_board, ats_type, status, error_category
                """
            ).fetchall()

        for row in rows:
            board = row[0] or "unknown"
            ats_type = row[1] or "unknown"
            status = row[2] or "unknown"
            error_category = row[3] or ""
            count = row[4]

            for _ in range(count):
                record_application_result(
                    board=board,
                    ats_type=ats_type,
                    success=(status == "submitted"),
                    blocker=error_category if status == "failed" else "",
                )

        logger.info(
            "Loaded performance metrics from DB: %d total, %.0f%% success rate",
            get_metrics().total_applications,
            get_metrics().success_rate,
        )

    except Exception as exc:
        logger.warning("Failed to load performance metrics from DB: %s", exc)


# ---------------------------------------------------------------------------
# Cron step functions
# ---------------------------------------------------------------------------


async def _step_heartbeat(client: MoltbookClient) -> bool:
    """Step 1: Check Moltbook API health."""
    alive = await client.heartbeat()
    if not alive:
        logger.warning("Moltbook heartbeat FAILED — skipping this cycle")
    else:
        logger.info("Moltbook heartbeat OK")
    return alive


async def _step_post_performance(client: MoltbookClient) -> None:
    """Step 2: Post anonymized performance update."""
    rl = get_rate_limiter()
    if not rl.can_post():
        logger.info(
            "Skipping performance post — cooldown (%.0fs remaining)",
            rl.seconds_until_next_post(),
        )
        return

    summary = generate_performance_summary()
    if "No applications tracked" in summary:
        logger.info("No performance data to share — skipping post")
        return

    # Sanitize outbound content
    safe_summary = sanitize_for_posting(summary, max_length=480)

    try:
        result = await client.create_post(safe_summary)
        post_id = str(result.get("id", ""))
        if post_id:
            _our_post_ids.append(post_id)
            if len(_our_post_ids) > _MAX_TRACKED_POSTS:
                _our_post_ids.pop(0)
        logger.info("Posted performance update (post_id=%s)", post_id)
    except ValueError as e:
        logger.info("Performance post skipped: %s", e)
    except Exception as exc:
        logger.warning("Failed to post performance update: %s", exc)


async def _step_scan_feed(client: MoltbookClient) -> List[Dict[str, Any]]:
    """Step 4: Scan Moltbook feed for relevant posts."""
    try:
        feed = await client.get_feed(page=1, limit=20)
        posts = feed.get("posts") or feed.get("data") or []
        if isinstance(posts, list):
            relevant = [p for p in posts if is_relevant_post(p)]
            logger.info(
                "Feed scan: %d posts total, %d relevant",
                len(posts), len(relevant),
            )

            # Process signals from relevant posts
            signal_count = process_feed_posts(relevant)
            logger.info("Extracted %d strategy signals from feed", signal_count)

            return relevant
        return []
    except Exception as exc:
        logger.warning("Failed to scan Moltbook feed: %s", exc)
        return []


async def _step_comment_helpfully(
    client: MoltbookClient,
    relevant_posts: List[Dict[str, Any]],
) -> None:
    """Step 5: Comment on relevant posts where we can add value."""
    rl = get_rate_limiter()
    comments_made = 0
    metrics = get_metrics()

    for post in relevant_posts:
        if comments_made >= MAX_COMMENTS_PER_CYCLE:
            break
        if not rl.can_comment():
            logger.info("Comment rate limit reached — stopping")
            break

        post_id = str(post.get("id", ""))
        if not post_id:
            continue

        # Skip our own posts
        if post_id in _our_post_ids:
            continue

        content = sanitize(
            post.get("content", ""),
            max_length=500,
            context=f"comment_candidate:{post_id}",
        )
        content_lower = content.lower()

        # Only comment if we have relevant expertise to share
        comment_text = _generate_helpful_comment(content_lower, metrics)
        if not comment_text:
            continue

        # Sanitize outbound
        safe_comment = sanitize_for_posting(comment_text, max_length=300)

        try:
            await client.comment(post_id, safe_comment)
            comments_made += 1
            logger.info("Commented on post %s (%d this cycle)", post_id, comments_made)
        except ValueError as e:
            logger.info("Comment skipped: %s", e)
            break
        except Exception as exc:
            logger.warning("Failed to comment on post %s: %s", post_id, exc)

    logger.info("Made %d comments this cycle", comments_made)


def _generate_helpful_comment(content_lower: str, metrics: Any) -> str:
    """Generate a helpful comment based on post content and our metrics.

    Returns empty string if we have nothing useful to contribute.
    SECURITY: Never includes PII, company names, or user data.
    """
    if metrics.total_applications == 0:
        return ""

    # Greenhouse insights
    if "greenhouse" in content_lower:
        gh_stats = metrics.ats_stats.get("greenhouse", {})
        if gh_stats.get("total", 0) >= 3:
            rate = gh_stats.get("success", 0) / gh_stats["total"] * 100
            return (
                f"From our experience with Greenhouse forms: "
                f"{rate:.0f}% success rate across {gh_stats['total']} attempts. "
                f"Custom question fields are the main complexity."
            )

    # Workday insights
    if "workday" in content_lower:
        wd_stats = metrics.ats_stats.get("workday", {})
        if wd_stats.get("total", 0) >= 3:
            rate = wd_stats.get("success", 0) / wd_stats["total"] * 100
            return (
                f"Workday forms: {rate:.0f}% success rate across {wd_stats['total']} attempts. "
                f"Multi-step wizards with file uploads are the challenge."
            )

    # CAPTCHA discussion
    if "captcha" in content_lower:
        captcha_count = metrics.blocker_counts.get("captcha", 0)
        if captcha_count > 0:
            return (
                f"We've hit CAPTCHAs {captcha_count} times recently. "
                f"Tends to happen more on high-traffic boards."
            )

    # General success rate if someone asks about conversion
    if any(kw in content_lower for kw in ["success rate", "conversion", "how many"]):
        return (
            f"Our current success rate is {metrics.success_rate:.0f}% "
            f"across {metrics.total_applications} applications. "
            f"Top board: {metrics.top_board}."
        )

    return ""


async def _step_check_engagement(client: MoltbookClient) -> None:
    """Step 6: Check engagement on our past posts."""
    if not _our_post_ids:
        return

    # Check the last 5 posts
    for post_id in _our_post_ids[-5:]:
        try:
            post_data = await client.get_post(post_id)
            comments = post_data.get("comments") or []
            votes = post_data.get("vote_count") or post_data.get("votes", 0)
            logger.info(
                "Post %s engagement: %d comments, %s votes",
                post_id, len(comments), votes,
            )

            # Process any comments on our posts as potential signals
            for comment in comments:
                comment_content = sanitize(
                    comment.get("content", ""),
                    max_length=500,
                    context=f"reply_to_us:{post_id}",
                )
                if comment_content and is_relevant_post({"content": comment_content}):
                    signals = extract_signals({"content": comment_content, "id": f"comment_{comment.get('id', '')}"})
                    for signal in signals:
                        from backend.moltbook.feedback_loop import process_signal
                        process_signal(signal)

        except Exception as exc:
            logger.debug("Failed to check engagement on post %s: %s", post_id, exc)


async def _step_update_strategy() -> None:
    """Step 7: Update strategy based on accumulated signals + performance."""
    try:
        update_strategies_from_performance()

        mgr = get_strategy_manager()
        state = mgr.get_state()
        accepted_count = len(mgr.get_accepted_patches())
        logger.info(
            "Strategy update complete: %d accepted patches, "
            "human_review_needed=%s, auto_adjustments=%d",
            accepted_count,
            state.human_review_needed,
            state.auto_adjustment_count,
        )

        if state.human_review_needed:
            logger.warning(
                "HUMAN REVIEW NEEDED: %d auto-adjustments accumulated. "
                "Strategy patches are suppressed until review.",
                state.auto_adjustment_count,
            )
    except Exception as exc:
        logger.warning("Strategy update failed: %s", exc)


# ---------------------------------------------------------------------------
# Main cron loop
# ---------------------------------------------------------------------------


def _cron_log_start() -> int | None:
    """Insert a 'running' row into cron_log and return its id."""
    try:
        from backend.shared.db import get_connection

        with get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cron_log (
                    id SERIAL PRIMARY KEY,
                    cron_name TEXT NOT NULL,
                    started_at TIMESTAMPTZ DEFAULT NOW(),
                    completed_at TIMESTAMPTZ,
                    status TEXT DEFAULT 'running',
                    details TEXT
                )
                """
            )
            row = conn.execute(
                "INSERT INTO cron_log (cron_name) VALUES ('moltbook') RETURNING id",
            ).fetchone()
            conn.commit()
            return row[0] if row else None
    except Exception as exc:
        logger.warning("cron_log insert failed: %s", exc)
        return None


def _cron_log_finish(log_id: int | None, status: str, details: str | None = None) -> None:
    """Update a cron_log row with final status."""
    if log_id is None:
        return
    try:
        from backend.shared.db import get_connection

        with get_connection() as conn:
            conn.execute(
                "UPDATE cron_log SET completed_at = NOW(), status = %s, details = %s WHERE id = %s",
                (status, details, log_id),
            )
            conn.commit()
    except Exception as exc:
        logger.warning("cron_log update failed: %s", exc)


async def run_cycle() -> None:
    """Execute one full Moltbook cron cycle."""
    logger.info("=== Moltbook cron cycle starting ===")
    start = time.time()
    client = MoltbookClient()
    log_id = _cron_log_start()

    try:
        # Step 1: Heartbeat
        if not await _step_heartbeat(client):
            _cron_log_finish(log_id, "skipped", "heartbeat failed")
            return

        # Load fresh performance data
        await _load_performance_from_db()

        # Step 2: Post performance update
        await _step_post_performance(client)

        # Step 3: (Share interesting findings is merged into step 2)

        # Step 4: Scan feed
        relevant_posts = await _step_scan_feed(client)

        # Step 5: Comment helpfully
        await _step_comment_helpfully(client, relevant_posts)

        # Step 6: Check engagement on past posts
        await _step_check_engagement(client)

        # Step 7: Update strategy
        await _step_update_strategy()

        # Step 8: Track cycle count and trigger dream cycle every 5th cycle
        global _cycle_count
        _cycle_count += 1

        if _cycle_count % DREAM_CYCLE_INTERVAL == 0:
            logger.info(
                "Step 8: Cycle %d -- entering dream cycle (sleep-time compute)...",
                _cycle_count,
            )
            try:
                from backend.moltbook.dream import run_dream_cycle
                await run_dream_cycle()
                logger.info("Dream cycle complete")
            except Exception as dream_exc:
                logger.error("Dream cycle failed: %s", dream_exc)
        else:
            logger.info(
                "Cycle %d -- next dream in %d cycles",
                _cycle_count,
                DREAM_CYCLE_INTERVAL - (_cycle_count % DREAM_CYCLE_INTERVAL),
            )

        elapsed = time.time() - start
        logger.info("=== Moltbook cron cycle complete (%.1fs) ===", elapsed)
        _cron_log_finish(log_id, "completed", f"{elapsed:.1f}s")

    except Exception as exc:
        logger.exception("Moltbook cron cycle failed: %s", exc)
        _cron_log_finish(log_id, "failed", str(exc))
    finally:
        await client.close()


async def run() -> None:
    """Entry point for the scheduler (single cycle)."""
    await run_cycle()


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------


async def _main_loop() -> None:
    """Run the cron loop forever (standalone mode)."""
    logger.info("Moltbook cron starting in standalone mode (interval=%ds)", CRON_INTERVAL_SECONDS)
    while True:
        await run_cycle()
        await asyncio.sleep(CRON_INTERVAL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main_loop())
