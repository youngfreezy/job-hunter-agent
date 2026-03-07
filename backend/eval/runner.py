"""CLI entry point for the RAGAS-style evaluation system.

Usage:
    python -m backend.eval.runner --session-id <id>
    python -m backend.eval.runner --all
    python -m backend.eval.runner --all --store-db
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from pathlib import Path

# Add project root to path so backend imports work
_project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_project_root))

from backend.eval.checkpoint_loader import (
    ensure_eval_table,
    list_session_ids,
    load_session_state,
    store_eval_result,
)
from backend.eval.judges import evaluate_session
from backend.eval.models import EvalResult

logger = logging.getLogger(__name__)

EVAL_RESULTS_DIR = _project_root / "eval_results"


async def run_eval(session_id: str, store_db: bool = False) -> EvalResult | None:
    """Evaluate a single session and return the result."""
    print(f"\n--- Evaluating session: {session_id} ---")

    state = await load_session_state(session_id)
    if state is None:
        print(f"  Session {session_id} not found in checkpoints.")
        return None

    # Print session summary
    keywords = state.get("keywords", [])
    discovered = len(state.get("discovered_jobs") or [])
    scored = len(state.get("scored_jobs") or [])
    submitted = len(state.get("applications_submitted") or [])
    print(f"  Keywords: {keywords}")
    print(f"  Discovered: {discovered}, Scored: {scored}, Submitted: {submitted}")

    # Run judges
    metrics = await evaluate_session(state)

    if not metrics:
        print("  No metrics produced (session may be incomplete).")
        return None

    # Compute overall score (weighted average)
    overall = sum(m.score for m in metrics) / len(metrics)

    result = EvalResult(
        session_id=session_id,
        eval_id=str(uuid.uuid4()),
        metrics=metrics,
        overall_score=overall,
        metadata={
            "keywords": keywords,
            "discovered_count": discovered,
            "scored_count": scored,
            "submitted_count": submitted,
            "status": state.get("status", "unknown"),
        },
    )

    # Print results
    print(f"\n  Overall Score: {overall:.2f}")
    print(f"  {'Metric':<30} {'Score':>6}  Reasoning")
    print(f"  {'-'*30} {'-'*6}  {'-'*50}")
    for m in metrics:
        reasoning_short = m.reasoning[:60] + "..." if len(m.reasoning) > 60 else m.reasoning
        print(f"  {m.name:<30} {m.score:>6.2f}  {reasoning_short}")

    # Save JSON report
    EVAL_RESULTS_DIR.mkdir(exist_ok=True)
    out_path = EVAL_RESULTS_DIR / f"{session_id}_{result.eval_id[:8]}.json"
    out_path.write_text(json.dumps(result.model_dump(), indent=2, default=str))
    print(f"\n  Report saved: {out_path}")

    # Store in DB if requested
    if store_db:
        try:
            await ensure_eval_table()
            await store_eval_result(result.model_dump())
            print("  Stored in eval_runs table.")
        except Exception as e:
            print(f"  Failed to store in DB: {e}")

    return result


async def main():
    parser = argparse.ArgumentParser(description="JobHunter Agent Evaluation Runner")
    parser.add_argument("--session-id", type=str, help="Evaluate a specific session")
    parser.add_argument("--all", action="store_true", help="Evaluate all sessions")
    parser.add_argument("--store-db", action="store_true", help="Store results in Postgres")
    args = parser.parse_args()

    if not args.session_id and not args.all:
        parser.error("Provide --session-id or --all")

    if args.session_id:
        await run_eval(args.session_id, store_db=args.store_db)
    elif args.all:
        session_ids = await list_session_ids()
        print(f"Found {len(session_ids)} sessions to evaluate.")
        results = []
        for sid in session_ids:
            r = await run_eval(sid, store_db=args.store_db)
            if r:
                results.append(r)

        if results:
            avg_overall = sum(r.overall_score for r in results) / len(results)
            print(f"\n{'='*60}")
            print(f"Evaluated {len(results)}/{len(session_ids)} sessions.")
            print(f"Average overall score: {avg_overall:.2f}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    asyncio.run(main())
