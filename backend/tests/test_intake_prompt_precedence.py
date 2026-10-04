"""A discovery prompt owns roles; resume analysis must not replace that search."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.orchestrator.agents import intake
from backend.shared.models.schemas import SearchConfig


@pytest.mark.asyncio
async def test_prompt_ignores_resume_keywords_and_places_core_role_before_three_unique_queries(monkeypatch):
    llm = MagicMock()
    monkeypatch.setattr(intake, 'build_llm', lambda **_: llm)
    monkeypatch.setattr('backend.shared.application_rules.load_application_rules', lambda _: '')
    extracted = SearchConfig(
        keywords=[' Applied AI Engineer ', 'AI ENGINEER', 'applied   ai engineer',
                  'AI Software Engineer', 'LLM Platform Engineer'],
        locations=['San Francisco'], experience_level='senior',
    ).model_copy(update={'primary_role': ' AI Engineer '})
    invoke = AsyncMock(return_value=extracted)
    monkeypatch.setattr(intake, 'invoke_with_retry', invoke)
    prompt = 'Find applied AI and AI-native software engineering roles, hybrid or remote in San Francisco.'
    result = await intake.run_intake_agent({
        'user_id': 'owner', 'keywords': ['Staff Full Stack Engineer', 'Database Administrator'],
        'resume_text': 'Ten years building production systems.',
        'preferences': {'discovery_prompt': prompt},
    })
    messages = invoke.await_args.args[1]
    llm.with_structured_output.assert_called_once_with(intake._PromptSearchConfig)
    assert 'Staff Full Stack Engineer' not in messages[1].content
    assert 'Database Administrator' not in messages[1].content
    assert prompt in messages[1].content
    assert 'Ten years building production systems.' in messages[1].content
    assert 'at most 6' not in messages[0].content
    assert result['keywords'] == ['AI Engineer', 'Applied AI Engineer', 'AI Software Engineer']
    assert result['search_config'].keywords == result['keywords']
    assert result['search_config'].experience_level == 'senior'
    assert type(result['search_config']) is SearchConfig
    invoke.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('prompt', [None, '', '   '])
async def test_keyword_search_without_prompt_keeps_legacy_schema_and_keywords(monkeypatch, prompt):
    llm = MagicMock()
    monkeypatch.setattr(intake, 'build_llm', lambda **_: llm)
    monkeypatch.setattr('backend.shared.application_rules.load_application_rules', lambda _: '')
    keywords = ['Platform Engineer', 'SRE', 'Cloud Engineer', 'DevOps Engineer']
    extracted = SearchConfig(keywords=keywords, locations=['Remote'])
    invoke = AsyncMock(return_value=extracted)
    monkeypatch.setattr(intake, 'invoke_with_retry', invoke)
    result = await intake.run_intake_agent({
        'keywords': keywords, 'preferences': {'discovery_prompt': prompt},
    })
    llm.with_structured_output.assert_called_once_with(SearchConfig)
    assert 'Keywords: Platform Engineer, SRE, Cloud Engineer, DevOps Engineer' in invoke.await_args.args[1][1].content
    assert result['keywords'] == keywords
    assert result['search_config'] is extracted


@pytest.mark.asyncio
async def test_blank_core_role_does_not_fall_back_to_resume_keywords(monkeypatch):
    monkeypatch.setattr(intake, 'build_llm', lambda **_: MagicMock())
    monkeypatch.setattr('backend.shared.application_rules.load_application_rules', lambda _: '')
    extracted = intake._PromptSearchConfig(
        primary_role='   ', keywords=[], locations=['San Francisco'])
    monkeypatch.setattr(intake, 'invoke_with_retry', AsyncMock(return_value=extracted))
    result = await intake.run_intake_agent({
        'keywords': ['Staff Full Stack Engineer'],
        'preferences': {'discovery_prompt': 'Find AI engineering roles.'},
    })
    assert 'search_config' not in result
    assert result['agent_statuses']['intake'] == 'failed'
