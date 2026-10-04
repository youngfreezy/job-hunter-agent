"""Hard eligibility is independent of a weighted fit score; no provider calls."""
from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest

from backend.orchestrator.agents import scoring
from backend.orchestrator.pipeline import graph
from backend.shared.models.schemas import JobListing, JobBoard, ScoredJob, SearchConfig


def listing(**changes):
    values = dict(id='job', title='ML Engineering Fellow', company='Example',
                  location='Remote', url='https://www.indeed.com/viewjob?jk=example',
                  board=JobBoard.INDEED, is_easy_apply=True, is_remote=True,
                  description_snippet='Production AI engineering. ' * 25 +
                  'Minimum15 years with bachelors or12 with masters or8 with PhD.')
    return JobListing(**{**values, **changes})


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(scoring, 'build_llm', lambda **kw: SimpleNamespace(with_structured_output=lambda schema: None))
    monkeypatch.setattr(scoring, 'emit_agent_event', AsyncMock())
    monkeypatch.setattr(scoring, 'get_active_prompt', lambda key: None)
    monkeypatch.setattr('backend.moltbook.strategies.get_strategy_patches', lambda: '')
    monkeypatch.setattr('backend.browser.fetch_verifier.verify_shortlist_candidates', AsyncMock(side_effect=lambda jobs, **kw: jobs))
    monkeypatch.setattr(graph, '_validate_job_urls', AsyncMock(side_effect=lambda jobs, *args, **kw: jobs))


@pytest.mark.asyncio
@pytest.mark.parametrize('verdict,expected', [('not_met', 0), ('unknown', 1), ('met', 1)])
async def test_fit_score_cannot_override_eligibility(monkeypatch, offline, verdict, expected):
    async def invoke(_, messages):
        return scoring.ScoringBatchResult(scores=[dict(job_id='job', score=99,
            score_breakdown=dict(keyword_match=99, location_match=100, salary_match=100, experience_match=99),
            eligibility_status=verdict, eligibility_reasons=['User-required work arrangement review.'])])
    monkeypatch.setattr(scoring, 'invoke_with_retry', invoke)
    result = await scoring.run_scoring_agent(dict(discovered_jobs=[listing()], resume_text='11 years experience.'))
    assert len(result['scored_jobs']) == expected
    if expected:
        assert result['scored_jobs'][0].eligibility_status == verdict
        assert result['scored_jobs'][0].eligibility_reasons == ['User-required work arrangement review.']


@pytest.mark.asyncio
async def test_scoring_sees_requirements_beyond_card_excerpt_and_original_facts(monkeypatch, offline):
    seen = []
    async def invoke(_, messages):
        seen.extend(messages)
        return scoring.ScoringBatchResult(scores=[dict(job_id='job', score=40,
            score_breakdown=dict(keyword_match=50, location_match=100, salary_match=50, experience_match=20),
            eligibility_status='not_met', eligibility_reasons=['User-required role does not match.'])])
    monkeypatch.setattr(scoring, 'invoke_with_retry', invoke)
    await scoring.run_scoring_agent(dict(discovered_jobs=[listing()], resume_text='Original: employment began November2015.',
        coached_resume='Polished summary omitting dates.', search_config=SearchConfig(keywords=['AI Engineer'],
        locations=['San Francisco'], remote_only=True, salary_min=220000, allow_unpublished_salary=True)))
    prompt = '\n'.join(m.content for m in seen)
    assert 'Minimum15 years' in prompt
    assert 'Original: employment began November2015.' in prompt
    assert '"remote_only": true' in prompt
    assert '"salary_min": 220000' in prompt
    assert '"allow_unpublished_salary": true' in prompt
    assert 'Current date (UTC):' in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize('preferences', [{'_autopilot_auto_approve':True}, {'_skip_coach_review':True}])
async def test_unknown_eligibility_requires_manual_review_even_with_high_score(monkeypatch, offline, preferences):
    state = dict(scored_jobs=[ScoredJob(job=listing(), score=99)], preferences=preferences)
    result = await graph.auto_approve_gate(state)
    assert result['application_queue'] == []
    assert graph._route_after_auto_approve_gate({**state, **result}) == 'shortlist_review'


@pytest.mark.asyncio
async def test_unknown_backfill_failure_is_not_automatically_retried(offline):
    from backend.shared.models.schemas import ApplicationResult, ApplicationStatus, ApplicationErrorCategory
    state = dict(scored_jobs=[ScoredJob(job=listing(), score=99)], backfill_rounds=1,
                 session_config={'minimum_submitted_applications':1},
                 applications_failed=[ApplicationResult(job_id='job',status=ApplicationStatus.FAILED,
                 error_category=ApplicationErrorCategory.TIMEOUT)])
    result = await graph.auto_approve_gate(state)
    assert result['application_queue'] == []
    assert result['active_retry_job_ids'] == []


def test_legacy_remote_only_discovery_does_not_accept_unproven_office_location():
    from backend.browser.tools.job_boards.indeed import matches_search
    search = SearchConfig(keywords=['AI Engineer'], locations=['Remote'], remote_only=True)
    assert not matches_search(listing(location='Santa Clara, CA', is_remote=False,
                              description_snippet='Build ML products.'), search)
    assert matches_search(listing(), search)


@pytest.mark.asyncio
async def test_remote_only_cannot_be_cleared_by_optimistic_model_and_permits_unpublished_pay(monkeypatch, offline):
    async def invoke(_, messages):
        return scoring.ScoringBatchResult(scores=[dict(job_id='job',score=99,
            eligibility_status='met', eligibility_reasons=[],
            score_breakdown=dict(keyword_match=99,location_match=100,salary_match=50,experience_match=99))])
    monkeypatch.setattr(scoring, 'invoke_with_retry', invoke)
    state = dict(resume_text='Original resume facts', search_config=SearchConfig(
        keywords=['AI Engineer'], locations=['San Francisco'], remote_only=True,
        salary_min=220000, allow_unpublished_salary=True))
    result = await scoring.run_scoring_agent({**state, 'discovered_jobs':[listing(
        location='Santa Clara, CA',is_remote=False,description_snippet='Build remote sensing systems.')]})
    assert result['scored_jobs'][0].eligibility_status == 'unknown'
    assert result['scored_jobs'][0].eligibility_reasons == ['The required work arrangement is not established by this listing.']
    result = await scoring.run_scoring_agent({**state, 'discovered_jobs':[listing()]})
    assert result['scored_jobs'][0].eligibility_status == 'met'
    assert not result['scored_jobs'][0].eligibility_reasons


@pytest.mark.asyncio
async def test_met_user_constraints_allow_autoapproval_despite_advertised_experience_gap(offline):
    state = dict(scored_jobs=[ScoredJob(job=listing(), score=70,eligibility_status='met',
                 reasons=['Less experience than advertised; related AI skills.'])],
                 preferences={'_autopilot_auto_approve':True})
    result = await graph.auto_approve_gate(state)
    assert result['application_queue'] == ['job']
    assert graph._route_after_auto_approve_gate({**state, **result}) == 'supervise_after_shortlist'


@pytest.mark.asyncio
async def test_known_unmet_user_constraint_never_autoapproved(offline):
    result = await graph.auto_approve_gate(dict(scored_jobs=[ScoredJob(job=listing(),score=99,
        eligibility_status='not_met')], preferences={'_autopilot_auto_approve':True}))
    assert result['application_queue'] == []


@pytest.mark.asyncio
async def test_manual_review_can_explicitly_select_unknown_but_not_known_failure(monkeypatch, offline):
    monkeypatch.setattr(graph, 'interrupt', lambda payload: {'approved_job_ids':['job','failed','not-in-shortlist']})
    state = dict(session_id='offline',scored_jobs=[ScoredJob(job=listing(),score=99),
                 ScoredJob(job=listing(id='failed'),score=99,eligibility_status='not_met')])
    result = await graph.shortlist_review_gate(state)
    assert result['application_queue'] == ['job']


@pytest.mark.asyncio
async def test_legacy_email_bulk_approval_only_selects_met_constraints(monkeypatch, offline):
    monkeypatch.setattr(graph, 'interrupt', lambda payload: {'approved_job_ids':'all'})
    state = dict(session_id='offline',application_queue=['old'],scored_jobs=[
        ScoredJob(job=listing(),score=99),
        ScoredJob(job=listing(id='met'),score=90,eligibility_status='met'),
        ScoredJob(job=listing(id='failed'),score=99,eligibility_status='not_met')])
    result = await graph.shortlist_review_gate(state)
    assert result['application_queue'] == ['met']
    state['scored_jobs'] = [state['scored_jobs'][0]]
    assert (await graph.shortlist_review_gate(state))['application_queue'] == []


def test_remote_only_explicit_in_person_contradiction_is_not_met():
    verdict, reasons = scoring._user_constraint_verdict(
        listing(location='On-site in Santa Clara, CA',is_remote=False),
        {'remote_only':True},'met',[])
    assert verdict == 'not_met'
    assert 'remote-only' in reasons[0]


@pytest.mark.asyncio
@pytest.mark.parametrize('approve_unknown', [False, True])
async def test_mixed_criteria_runs_met_first_then_reviews_unknown_once(monkeypatch, offline, approve_unknown):
    """Real checkpoint/interrupt routing with only application effects faked."""
    from langgraph.graph import StateGraph, START, END
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.types import Command
    from backend.orchestrator.pipeline.state import JobHunterState
    from backend.shared.models.schemas import ApplicationResult, ApplicationStatus
    applied = []
    async def apply(state):
        done = {r.job_id for r in state.get('applications_submitted', [])}
        pending = [jid for jid in state['application_queue'] if jid not in done]
        applied.extend(pending)
        return {'applications_submitted':[ApplicationResult(job_id=jid,status=ApplicationStatus.SUBMITTED) for jid in pending]}
    workflow = StateGraph(JobHunterState)
    workflow.add_node('auto', graph.auto_approve_gate)
    workflow.add_node('apply', apply)
    workflow.add_node('review', graph.shortlist_review_gate)
    workflow.add_edge(START, 'auto')
    workflow.add_conditional_edges('auto', graph._route_after_auto_approve_gate,
                                  {'supervise_after_shortlist':'apply','shortlist_review':'review'})
    workflow.add_conditional_edges('apply', graph.route_after_application,
                                  {'verification':END,'shortlist_review':'review','application':'apply','auto_approve_gate':'auto'})
    workflow.add_edge('review','apply')
    runner = workflow.compile(checkpointer=MemorySaver())
    config = {'configurable':{'thread_id':f'mixed-{approve_unknown}'}}
    await runner.ainvoke({'session_id':'offline','preferences':{'_autopilot_auto_approve':True},
                        'scored_jobs':[ScoredJob(job=listing(id='met'),score=90,eligibility_status='met'),
                                       ScoredJob(job=listing(id='unknown'),score=99)]},config)
    assert applied == ['met']
    snapshot = await runner.aget_state(config)
    assert snapshot.values['pending_eligibility_review_ids'] == ['unknown']
    assert snapshot.next == ('review',)
    assert [job['job']['id'] for job in snapshot.tasks[0].interrupts[0].value['scored_jobs']] == ['unknown']
    await runner.ainvoke(Command(resume={'approved_job_ids':['unknown'] if approve_unknown else []}),config)
    snapshot = await runner.aget_state(config)
    assert snapshot.next == ()
    assert snapshot.values['pending_eligibility_review_ids'] == []
    assert applied == (['met','unknown'] if approve_unknown else ['met'])
    assert snapshot.values.get('applications_skipped', []) == ([] if approve_unknown else ['unknown'])
    # A later backfill/circuit-breaker revisit cannot requeue either outcome.
    revisit = await graph.auto_approve_gate({**snapshot.values, 'backfill_rounds':1})
    assert revisit['pending_eligibility_review_ids'] == []
    assert revisit['application_queue'] == []


def test_review_projection_matches_serialized_checkpoint_subset():
    state = {'pending_eligibility_review_ids':['unknown'], 'scored_jobs':[
        ScoredJob(job=listing(id='met'),score=99,eligibility_status='met').model_dump(),
        ScoredJob(job=listing(id='unknown'),score=50).model_dump()]}
    assert [sj['job']['id'] for sj in graph.shortlist_candidates(state)] == ['unknown']
