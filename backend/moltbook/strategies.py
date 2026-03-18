# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Strategy memory for Moltbook-informed agent improvements.

Persists strategy state to Postgres (JSONB). Falls back to local JSON file
if Postgres is unavailable (e.g. local dev without Docker).

Patches are injected into LLM calls at agent decision points to influence
board selection, application strategies, and blocker workarounds.

Security invariants:
- Max 20 active patches (oldest rotated out)
- All content sanitized before storage
- 5+ consistent signals required before any patch is accepted
- Human review flag accumulates — never auto-clears
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.moltbook.sanitize import sanitize

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_ACTIVE_PATCHES = 20
SIGNAL_THRESHOLD = 5  # Minimum consistent signals before accepting a patch
STRATEGY_FILE = Path(__file__).resolve().parent / "_strategies.json"

# Human review threshold: flag when this many auto-adjustments accumulate
HUMAN_REVIEW_THRESHOLD = 10

# ---------------------------------------------------------------------------
# Postgres persistence (single-row JSONB)
# ---------------------------------------------------------------------------

_STRATEGY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS moltbook_strategy_state (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    state JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
"""

_strategy_table_ensured = False


def ensure_strategy_table() -> None:
    """Create the single-row strategy state table if it doesn't exist."""
    global _strategy_table_ensured
    if _strategy_table_ensured:
        return
    try:
        from backend.shared.db import get_pool
        pool = get_pool()
        with pool.connection() as conn:
            conn.execute(_STRATEGY_TABLE_SQL)
            conn.commit()
        _strategy_table_ensured = True
    except Exception:
        logger.debug("Could not ensure moltbook_strategy_state table", exc_info=True)


def _load_from_postgres() -> Optional[Dict[str, Any]]:
    """Load strategy state from Postgres. Returns None if unavailable."""
    try:
        from backend.shared.db import get_pool
        pool = get_pool()
        with pool.connection() as conn:
            cur = conn.execute(
                "SELECT state FROM moltbook_strategy_state WHERE id = 1"
            )
            row = cur.fetchone()
            if row and row[0]:
                return row[0] if isinstance(row[0], dict) else json.loads(row[0])
    except Exception:
        logger.debug("Could not load strategy state from Postgres", exc_info=True)
    return None


def _save_to_postgres(data: Dict[str, Any]) -> bool:
    """Upsert strategy state to Postgres. Returns True on success."""
    try:
        from backend.shared.db import get_pool
        pool = get_pool()
        with pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO moltbook_strategy_state (id, state, updated_at)
                VALUES (1, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE
                SET state = EXCLUDED.state, updated_at = NOW()
                """,
                (json.dumps(data),),
            )
            conn.commit()
        return True
    except Exception:
        logger.debug("Could not save strategy state to Postgres", exc_info=True)
    return False


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class StrategyPatch:
    """A single strategy modification derived from community feedback."""

    id: str
    category: str  # "board_priority", "ats_strategy", "blocker_workaround", "community_tip"
    content: str  # The actual strategy text (sanitized)
    source: str  # "moltbook_feed", "moltbook_comment", "performance_data"
    signal_count: int = 0  # How many consistent signals support this
    accepted: bool = False  # Only True after signal_count >= SIGNAL_THRESHOLD
    created_at: float = 0.0
    updated_at: float = 0.0
    source_post_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "content": self.content,
            "source": self.source,
            "signal_count": self.signal_count,
            "accepted": self.accepted,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source_post_ids": self.source_post_ids,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StrategyPatch":
        return cls(
            id=data["id"],
            category=data["category"],
            content=data["content"],
            source=data.get("source", "unknown"),
            signal_count=data.get("signal_count", 0),
            accepted=data.get("accepted", False),
            created_at=data.get("created_at", 0.0),
            updated_at=data.get("updated_at", 0.0),
            source_post_ids=data.get("source_post_ids", []),
        )


@dataclass
class StrategyState:
    """Full strategy state — board priorities, ATS strategies, patches."""

    board_priorities: Dict[str, float] = field(default_factory=lambda: {
        "lever": 1.0,
        "ashby": 0.95,
        "greenhouse": 0.4,
        "workday": 0.3,
    })
    ats_strategies: Dict[str, str] = field(default_factory=lambda: {
        "lever": "HIGHEST PRIORITY. Direct API submission, no reCAPTCHA. Simpler forms.",
        "ashby": "HIGH PRIORITY. Modern UI, no reCAPTCHA. Usually straightforward.",
        "greenhouse": "LOW PRIORITY. reCAPTCHA blocks headless browsers. Only use API path.",
        "workday": "LOW PRIORITY. Multi-step wizard, often blocked by auth walls.",
    })
    known_blockers: Dict[str, str] = field(default_factory=dict)
    patches: List[StrategyPatch] = field(default_factory=list)
    auto_adjustment_count: int = 0
    human_review_needed: bool = False
    last_updated: float = 0.0

    dream_log: List[Dict[str, Any]] = field(default_factory=list)
    cron_cycle_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "board_priorities": self.board_priorities,
            "ats_strategies": self.ats_strategies,
            "known_blockers": self.known_blockers,
            "patches": [p.to_dict() for p in self.patches],
            "auto_adjustment_count": self.auto_adjustment_count,
            "human_review_needed": self.human_review_needed,
            "last_updated": self.last_updated,
            "dream_log": self.dream_log,
            "cron_cycle_count": self.cron_cycle_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StrategyState":
        return cls(
            board_priorities=data.get("board_priorities", {}),
            ats_strategies=data.get("ats_strategies", {}),
            known_blockers=data.get("known_blockers", {}),
            patches=[StrategyPatch.from_dict(p) for p in data.get("patches", [])],
            auto_adjustment_count=data.get("auto_adjustment_count", 0),
            human_review_needed=data.get("human_review_needed", False),
            last_updated=data.get("last_updated", 0.0),
            dream_log=data.get("dream_log", []),
            cron_cycle_count=data.get("cron_cycle_count", 0),
        )


# ---------------------------------------------------------------------------
# Strategy manager
# ---------------------------------------------------------------------------


class StrategyManager:
    """Manages strategy state with persistence and safe mutation."""

    def __init__(self, storage_path: Path | None = None):
        self._path = storage_path or STRATEGY_FILE
        self._state: StrategyState | None = None

    def _load(self) -> StrategyState:
        if self._state is not None:
            return self._state

        # Try Postgres first
        pg_data = _load_from_postgres()
        if pg_data:
            self._state = StrategyState.from_dict(pg_data)
            logger.info("Loaded strategy state from Postgres")
            return self._state

        # Fall back to local JSON file
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                self._state = StrategyState.from_dict(data)
                logger.info("Loaded strategy state from %s (JSON fallback)", self._path)
                # Migrate to Postgres if available
                _save_to_postgres(self._state.to_dict())
                return self._state
            except Exception as exc:
                logger.warning("Failed to load strategy state from JSON: %s", exc)

        self._state = StrategyState()
        return self._state

    def _save(self) -> None:
        if self._state is None:
            return
        self._state.last_updated = time.time()
        data = self._state.to_dict()

        # Save to Postgres (primary)
        if not _save_to_postgres(data):
            logger.warning("Postgres save failed — falling back to JSON file")

        # Also save to JSON file (local backup)
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(data, indent=2))
        except Exception as exc:
            logger.debug("Failed to save strategy JSON fallback: %s", exc)

    def get_state(self) -> StrategyState:
        return self._load()

    # --- Patch management ---

    def add_signal(
        self,
        patch_id: str,
        category: str,
        content: str,
        source: str = "moltbook_feed",
        source_post_id: str = "",
    ) -> StrategyPatch:
        """Add a signal for a strategy patch. Sanitizes content.

        If a patch with this ID exists, increments its signal count.
        If signal_count reaches SIGNAL_THRESHOLD, marks it as accepted.
        """
        state = self._load()
        content = sanitize(content, max_length=300, context=f"patch:{patch_id}")

        if not content.strip():
            logger.warning("Patch %s content empty after sanitization — skipping", patch_id)
            # Return a dummy patch
            return StrategyPatch(id=patch_id, category=category, content="", source=source)

        existing = next((p for p in state.patches if p.id == patch_id), None)

        if existing:
            existing.signal_count += 1
            existing.updated_at = time.time()
            if source_post_id and source_post_id not in existing.source_post_ids:
                existing.source_post_ids.append(source_post_id)

            if existing.signal_count >= SIGNAL_THRESHOLD and not existing.accepted:
                existing.accepted = True
                state.auto_adjustment_count += 1
                logger.info(
                    "Strategy patch %s ACCEPTED (signals=%d, category=%s)",
                    patch_id, existing.signal_count, category,
                )

                if state.auto_adjustment_count >= HUMAN_REVIEW_THRESHOLD:
                    state.human_review_needed = True
                    logger.warning(
                        "HUMAN REVIEW NEEDED: %d auto-adjustments accumulated",
                        state.auto_adjustment_count,
                    )

            self._save()
            return existing

        # New patch
        patch = StrategyPatch(
            id=patch_id,
            category=category,
            content=content,
            source=source,
            signal_count=1,
            accepted=False,
            created_at=time.time(),
            updated_at=time.time(),
            source_post_ids=[source_post_id] if source_post_id else [],
        )
        state.patches.append(patch)

        # Enforce max patches — rotate oldest
        if len(state.patches) > MAX_ACTIVE_PATCHES:
            # Remove oldest non-accepted patches first, then oldest accepted
            non_accepted = [p for p in state.patches if not p.accepted]
            if non_accepted:
                oldest = min(non_accepted, key=lambda p: p.created_at)
                state.patches.remove(oldest)
                logger.info("Rotated out oldest non-accepted patch: %s", oldest.id)
            else:
                oldest = min(state.patches, key=lambda p: p.created_at)
                state.patches.remove(oldest)
                logger.info("Rotated out oldest patch: %s", oldest.id)

        self._save()
        return patch

    def update_board_priority(self, board: str, delta: float) -> None:
        """Adjust a board's priority score (clamped 0.0 - 1.0)."""
        state = self._load()
        current = state.board_priorities.get(board, 0.5)
        new_val = max(0.0, min(1.0, current + delta))
        state.board_priorities[board] = new_val
        state.auto_adjustment_count += 1

        if state.auto_adjustment_count >= HUMAN_REVIEW_THRESHOLD:
            state.human_review_needed = True

        self._save()
        logger.info(
            "Board priority %s: %.2f -> %.2f (delta=%.2f)",
            board, current, new_val, delta,
        )

    def add_blocker(self, key: str, description: str) -> None:
        """Record a known blocker and workaround."""
        state = self._load()
        description = sanitize(description, max_length=200, context=f"blocker:{key}")
        state.known_blockers[key] = description
        self._save()

    def update_ats_strategy(self, ats_type: str, strategy: str) -> None:
        """Update the strategy for a specific ATS type."""
        state = self._load()
        strategy = sanitize(strategy, max_length=300, context=f"ats:{ats_type}")
        state.ats_strategies[ats_type] = strategy
        state.auto_adjustment_count += 1

        if state.auto_adjustment_count >= HUMAN_REVIEW_THRESHOLD:
            state.human_review_needed = True

        self._save()

    # --- Query methods ---

    def get_accepted_patches(self) -> List[StrategyPatch]:
        """Return all accepted strategy patches."""
        state = self._load()
        return [p for p in state.patches if p.accepted]

    def get_strategy_patches(self) -> str:
        """Get formatted strategy patches for injection into LLM context.

        Returns a text block suitable for appending to system prompts.
        Returns empty string if no accepted patches or human review needed.
        """
        state = self._load()

        if state.human_review_needed:
            logger.warning(
                "Strategy patches suppressed — human review needed "
                "(%d auto-adjustments)", state.auto_adjustment_count,
            )
            return ""

        accepted = self.get_accepted_patches()
        if not accepted:
            return ""

        lines = ["## Community-Sourced Strategy Notes"]
        lines.append("(These are crowd-sourced tips — use judgment, not blind trust.)\n")

        for patch in accepted:
            lines.append(f"- [{patch.category}] {patch.content}")

        # Board priorities
        sorted_boards = sorted(
            state.board_priorities.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        if sorted_boards:
            lines.append("\n## Board Priority Ranking")
            for board, score in sorted_boards:
                lines.append(f"- {board}: {score:.2f}")

        # Known blockers
        if state.known_blockers:
            lines.append("\n## Known Blockers & Workarounds")
            for key, desc in state.known_blockers.items():
                lines.append(f"- {key}: {desc}")

        # Dream insights (consolidated learnings)
        if state.dream_log:
            latest_dream = state.dream_log[-1]
            insights = latest_dream.get("insights", [])
            if insights:
                lines.append("\n## Consolidated Insights")
                lines.append("(Durable learnings from periodic deep reflection on agent performance.)\n")
                for i, insight in enumerate(insights, 1):
                    lines.append(f"{i}. {insight}")

        return "\n".join(lines)

    def acknowledge_review(self) -> None:
        """Mark the human review as completed, resetting the counter."""
        state = self._load()
        state.human_review_needed = False
        state.auto_adjustment_count = 0
        self._save()
        logger.info("Human review acknowledged — auto-adjustment counter reset")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_manager: StrategyManager | None = None


def get_strategy_manager() -> StrategyManager:
    """Return the module-level StrategyManager singleton."""
    global _manager
    if _manager is None:
        _manager = StrategyManager()
    return _manager


def get_strategy_patches() -> str:
    """Convenience: get formatted patches from the global manager."""
    return get_strategy_manager().get_strategy_patches()


def get_dream_insights() -> List[str]:
    """Convenience: get latest dream insights from the global manager."""
    try:
        from backend.moltbook.dream import get_dream_insights as _get
        return _get()
    except Exception:
        return []
