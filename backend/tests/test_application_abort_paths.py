"""The application node's abort paths on the Browserbase branch.

Browserbase mode drives the Playwright appliers; Skyvern stays behind
SKYVERN_ENABLED=false.  A Skyvern failure, including its credits-exhausted
marker, is therefore an ordinary FAILED result for the LLM supervisor to weigh,
not a session-wide abort that pauses every remaining application.
"""

from __future__ import annotations

import inspect

from backend.orchestrator.agents import application as application_mod


def test_skyvern_credits_marker_no_longer_aborts_the_session():
    src = inspect.getsource(application_mod)
    assert "skyvern_credits_exhausted" not in src
    assert not hasattr(application_mod, "_alert_skyvern_credits_exhausted")
    assert not hasattr(application_mod, "_skyvern_sse_alerted")
    assert not hasattr(application_mod, "_skyvern_notified")


def test_failed_results_still_reach_the_supervisor():
    """Both apply loops hand every FAILED result to the supervisor."""
    src = inspect.getsource(application_mod.run_application_agent)
    assert src.count("await _call_application_supervisor(") >= 2
    assert "aborted — Skyvern credits exhausted" not in src
