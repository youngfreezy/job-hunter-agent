# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Evaluation data models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EvalMetric(BaseModel):
    """A single evaluation metric result."""
    name: str
    score: float = Field(ge=0.0, le=1.0)
    reasoning: str
    agent: str  # "coach", "discovery", "scoring", "tailor", "e2e"


class EvalResult(BaseModel):
    """Full evaluation result for a session."""
    session_id: str
    eval_id: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    metrics: List[EvalMetric]
    overall_score: float = Field(ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GoldenExample(BaseModel):
    """A curated test case with expected quality scores."""
    session_id: str
    description: str
    expected_scores: Dict[str, float] = Field(default_factory=dict)
    # e.g. {"coach_faithfulness": 0.9, "discovery_relevance": 0.8}
