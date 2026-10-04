"""Interview prep must never manufacture a successful empty result or grade."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from backend.gateway.routes import interview_prep as routes
from backend.orchestrator.interview_prep import graph
from backend.shared import llm, model_access


@pytest.fixture
def provider(monkeypatch):
    model = MagicMock()
    monkeypatch.setattr(llm, 'build_llm', lambda **kwargs: model)
    invoke = AsyncMock(return_value=SimpleNamespace(content='not valid json'))
    monkeypatch.setattr(llm, 'invoke_with_retry', invoke)
    return model, invoke


@pytest.mark.asyncio
@pytest.mark.parametrize('node', [graph.company_research_node, graph.question_generator_node])
async def test_invalid_provider_output_never_becomes_empty_success(provider, node):
    with pytest.raises(Exception):
        await node({'company': 'Fixture', 'role': 'Engineer', 'resume_text': 'Facts'})


@pytest.fixture
def prep(monkeypatch):
    monkeypatch.setattr(routes, 'get_model_user', lambda req: {'id': 'owner'})
    monkeypatch.setattr(model_access, 'require_model_access', lambda owner: None)
    meta = {'user_id': 'owner', 'status': 'starting', 'questions': [
        {'id': 'q1', 'category': 'behavioral', 'question': 'Describe a project.'}],
        'questions_answered': 0, 'grades': [], 'coaching_cache': {}}
    monkeypatch.setattr(routes, '_prep_registry', {'fixture': meta})
    monkeypatch.setattr(routes, '_prep_events', {'fixture': []})
    monkeypatch.setattr(routes, '_prep_subscribers', {})
    return meta


@pytest.mark.asyncio
async def test_invalid_grade_does_not_consume_allowance_or_append_fabricated_scores(provider, prep):
    with pytest.raises(HTTPException) as error:
        await routes.submit_answer(None, 'fixture', routes.SubmitAnswerRequest(question_id='q1', answer='My answer'))
    assert error.value.status_code == 502
    assert prep['grades'] == []
    assert prep['questions_answered'] == 0
    assert routes._prep_events['fixture'] == []


@pytest.mark.asyncio
async def test_invalid_coaching_is_not_cached(provider, prep):
    with pytest.raises(HTTPException) as error:
        await routes.get_coaching(None, 'fixture', routes.CoachRequest(question_id='q1'))
    assert error.value.status_code == 502
    assert prep['coaching_cache'] == {}


@pytest.mark.asyncio
async def test_empty_graph_does_not_emit_ready(prep):
    class EmptyGraph:
        async def astream(self, *args, **kwargs):
            yield {'data': {'status': 'starting', 'questions': []}}
    await routes._run_prep_pipeline('fixture', EmptyGraph(), {}, {'user_id': 'owner'})
    assert prep['status'] == 'failed'
    events = routes._prep_events['fixture']
    assert not any(e['type'] == 'ready_for_practice' for e in events)
    assert events[-1]['type'] == 'error'


def brief():
    return {'mission': 'Cloud browsers', 'culture': 'Unknown; verify directly.',
            'things_to_mention': ['Discuss browser reliability.'], 'interview_tips': ['Give examples.']}


def questions():
    return {'questions': [{'category': 'technical', 'question': f'How would you test system {i}?'}
                          for i in range(15)]}


@pytest.mark.asyncio
async def test_real_graph_structured_results_reach_ready_with_unique_questions(provider, prep):
    from backend.orchestrator.interview_prep.contracts import CompanyBrief, QuestionSet
    model, invoke = provider
    invoke.side_effect = [brief(), questions()]
    await routes._run_prep_pipeline('fixture', graph.build_interview_prep_graph(), {},
                                   {'user_id': 'owner', 'status': 'starting', 'company': 'Fixture', 'role': 'Engineer'})
    assert prep['status'] == 'ready'
    assert len(prep['questions']) == len({q['id'] for q in prep['questions']}) == 15
    assert all(q['source'] == 'ai_generated' for q in prep['questions'])
    events = routes._prep_events['fixture']
    assert [e['data']['status'] for e in events if e['type'] == 'status'] == ['researching', 'generating_questions']
    assert events[-1]['type'] == 'ready_for_practice'
    assert [c.args[0] for c in model.with_structured_output.call_args_list] == [CompanyBrief, QuestionSet]
    assert 'No live web retrieval' in invoke.await_args_list[0].args[1][0].content
    emitted_brief = next(e['data'] for e in events if e['type'] == 'company_brief')
    assert emitted_brief['recent_news'] == 'No live news verified.'
    assert emitted_brief['glassdoor_rating'] is None


@pytest.mark.asyncio
async def test_registry_tracks_progress_before_questions_finish(provider, prep):
    async def response(model, messages):
        if 'company briefing' in messages[0].content:
            return brief()
        assert prep['status'] == 'generating_questions'
        return questions()
    provider[1].side_effect = response
    await routes._run_prep_pipeline('fixture', graph.build_interview_prep_graph(), {}, {'user_id': 'owner'})
    assert prep['status'] == 'ready'


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['grade', 'coach'])
async def test_budget_stop_preserves_no_grade_no_cache_no_allowance(provider, prep, operation):
    from backend.shared.model_budget import BudgetStopped
    provider[1].side_effect = BudgetStopped('Model spend ceiling reached; paid request blocked.')
    with pytest.raises(BudgetStopped):
        if operation == 'grade':
            await routes.submit_answer(None, 'fixture', routes.SubmitAnswerRequest(question_id='q1', answer='Answer'))
        else:
            await routes.get_coaching(None, 'fixture', routes.CoachRequest(question_id='q1'))
    assert prep['questions_answered'] == 0
    assert prep['grades'] == [] and prep['coaching_cache'] == {}


@pytest.mark.asyncio
async def test_background_budget_failure_is_safe_and_not_ready(provider, prep):
    from backend.shared.model_budget import BudgetStopped
    provider[1].side_effect = BudgetStopped('secret provider diagnostic')
    await routes._run_prep_pipeline('fixture', graph.build_interview_prep_graph(), {}, {'user_id': 'owner'})
    assert prep['status'] == 'failed'
    assert prep['error_category'] == 'budget_stopped'
    assert 'secret' not in str(routes._prep_events['fixture'])
    assert not any(e['type'] == 'ready_for_practice' for e in routes._prep_events['fixture'])


@pytest.mark.asyncio
async def test_valid_grade_and_coaching_preserve_frontend_shape(provider, prep):
    grade = dict.fromkeys(['relevance', 'specificity', 'star_structure', 'confidence', 'overall'], 8)
    grade.update(feedback='Add a measured result.', strong_answer_example='Explain your actual result.')
    coaching = {'resume_highlights': [], 'star_scaffold': dict.fromkeys(['situation','task','action','result'], 'Supply your own example.'),
                'key_points': ['Be specific.'], 'pitfalls': ['Avoid invented metrics.']}
    provider[1].side_effect = [grade, coaching]
    result = await routes.submit_answer(None, 'fixture', routes.SubmitAnswerRequest(question_id='q1', answer='Answer'))
    assert result['grade'] == dict(grade, question_id='q1')
    assert result['questions_answered'] == 1
    assert await routes.get_coaching(None, 'fixture', routes.CoachRequest(question_id='q1')) == coaching
    assert prep['coaching_cache']['q1'] == coaching


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid', [{}, {'questions': []}, {'questions': [{'question': 'Uncategorized'}]}])
async def test_incomplete_question_sets_are_rejected(provider, invalid):
    provider[1].return_value = invalid
    with pytest.raises(Exception):
        await graph.question_generator_node({})


@pytest.mark.asyncio
async def test_out_of_range_scores_do_not_consume_allowance(provider, prep):
    provider[1].return_value = dict(relevance=99, specificity=5, star_structure=5, confidence=5, overall=5,
                                    feedback='Feedback', strong_answer_example='Example')
    with pytest.raises(HTTPException):
        await routes.submit_answer(None, 'fixture', routes.SubmitAnswerRequest(question_id='q1', answer='Answer'))
    assert prep['grades'] == [] and prep['questions_answered'] == 0


@pytest.mark.asyncio
async def test_replayed_error_ends_stream_and_releases_subscriber(monkeypatch, prep):
    monkeypatch.setattr(routes, 'get_owned_registry_session', lambda *args: None)
    routes._emit_prep('fixture', 'error', {'message': 'Please retry.'})
    response = await routes.stream_prep(None, 'fixture')
    stream = response.body_iterator
    assert 'event: error' in await anext(stream)
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    assert routes._prep_subscribers['fixture'] == []
