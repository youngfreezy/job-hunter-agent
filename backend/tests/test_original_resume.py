from unittest.mock import patch

import pytest

from backend.orchestrator.pipeline.graph import coach_review_gate


@pytest.mark.asyncio
async def test_original_resume_choice_preserves_canonical_content():
    state = {
        'session_id': 'test',
        'resume_text': 'Canonical resume, verbatim.',
        'coached_resume': 'Rewritten resume.',
        'coach_output': None,
    }
    from unittest.mock import Mock
    state['coach_output'] = Mock()
    with patch('backend.orchestrator.pipeline.graph.interrupt', return_value={'approved': True, 'use_original': True}):
        update = await coach_review_gate(state)
    assert update['coached_resume'] == state['resume_text']


def test_session_supports_twenty_application_demo():
    from backend.shared.models.schemas import SessionConfig
    from pydantic import ValidationError
    assert SessionConfig(max_jobs=20).max_jobs == 20
    with pytest.raises(ValidationError):
        SessionConfig(max_jobs=21)
