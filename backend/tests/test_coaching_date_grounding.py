"""Coaching receives the runtime date without changing the uploaded chronology."""
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.orchestrator.agents import career_coach, coach_chat
from backend.shared.models.schemas import CoachOutput, ResumeScore
from backend.shared import coaching_context


RESUME = 'Candidate\nEngineer, July 2026 – August 2026\nBuilt production systems.'


def output():
    return CoachOutput(
        rewritten_resume=RESUME, resume_score=ResumeScore(
            overall=80, keyword_density=80, impact_metrics=80,
            ats_compatibility=80, readability=80, formatting=80),
        cover_letter_template='Dear team,', confidence_message='Your experience is useful.',
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('interactive', [False, True])
async def test_every_coaching_invocation_supplies_trusted_today_and_preserves_resume(monkeypatch, interactive):
    class FixedClock:
        @staticmethod
        def now(tz):
            assert tz is timezone.utc
            return datetime(2026, 10, 4, tzinfo=tz)
    monkeypatch.setattr(coaching_context, 'datetime', FixedClock)
    agent = coach_chat if interactive else career_coach
    monkeypatch.setattr(agent, 'build_llm', lambda **_: MagicMock())
    monkeypatch.setattr(agent, 'premium_model', lambda: 'mock-model')
    result = coach_chat.CoachChatResult(response_message='Reviewed.', coach_output=output()) if interactive else output()
    invoke = AsyncMock(return_value=result)
    monkeypatch.setattr(agent, 'invoke_with_retry', invoke)
    if interactive:
        await coach_chat.revise_coach_output(original_resume=RESUME, current_output=output(),
                                            latest_user_message='Review my dates.', chat_history=[])
    else:
        monkeypatch.setattr(career_coach, 'emit_agent_event', AsyncMock())
        state = {'resume_text': RESUME, 'session_id': 'fixture'}
        await career_coach.run_career_coach_agent(state)
        assert state['resume_text'] == RESUME
    messages = invoke.await_args.args[1]
    assert 'Current date (UTC): 2026-10-04' in messages[0].content
    assert 'Preserve the resume’s original dates' in messages[0].content
    if interactive:
        assert json.loads(messages[1].content)['original_resume'] == RESUME
    else:
        assert f'--- BEGIN RESUME ---\n{RESUME}\n--- END RESUME ---' in messages[1].content


def test_date_context_refreshes_after_worker_crosses_year_boundary(monkeypatch):
    clock = MagicMock()
    clock.now.side_effect = [datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc),
                             datetime(2027, 1, 1, 0, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr(coaching_context, 'datetime', clock)
    assert 'Current date (UTC): 2026-12-31' in coaching_context.coaching_date_context()
    assert 'Current date (UTC): 2027-01-01' in coaching_context.coaching_date_context()
    assert clock.now.call_count == 2
