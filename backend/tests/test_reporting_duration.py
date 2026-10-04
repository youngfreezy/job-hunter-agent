from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.orchestrator.agents import reporting


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 4, 0, 6, 26, tzinfo=timezone.utc)


@pytest.mark.asyncio
@pytest.mark.parametrize('timestamps,expected', [
    ({'created_at': '2026-10-04T00:00:00+00:00'}, 6),
    ({'created_at': '2026-10-04T00:00:00+00:00', 'session_start_time': None}, 6),
    ({'created_at': '2026-10-04T00:00:00+00:00', 'session_start_time': '2026-10-04T00:02:00+00:00'}, 4),
    ({'created_at': '2026-10-04T00:06:00+00:00'}, 0),
])
async def test_reporting_duration_uses_gateway_start_and_preserves_legacy_start(monkeypatch, timestamps, expected):
    monkeypatch.setattr(reporting, 'datetime', FixedDateTime)
    monkeypatch.setattr(reporting, 'emit_agent_event', AsyncMock())
    monkeypatch.setattr(reporting, '_build_llm', MagicMock())
    monkeypatch.setattr(reporting, 'invoke_with_retry', AsyncMock(return_value=reporting.NextStepsResult(next_steps=[])))
    monkeypatch.setattr('backend.shared.outcome_store.record_outcome', MagicMock())
    monkeypatch.setattr('backend.shared.outcome_store.get_outcome_count', lambda: 0)
    monkeypatch.setattr('backend.optimization.application_feedback.refresh_all_strategies', lambda: None)
    result = await reporting.run_reporting_agent({'session_id': 'duration-fixture', **timestamps})
    assert result['status'] == 'completed'
    assert result['session_summary'].duration_minutes == expected
