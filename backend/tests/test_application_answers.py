"""Grounding checks gate browser actions; no live model or browser calls."""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.browser import application_answers as answers
from backend.shared.application_rules import ApplicationParked


def checker(monkeypatch, result):
    invoke = AsyncMock(return_value=result)
    model = MagicMock()
    model.with_structured_output.return_value.ainvoke = invoke
    build = MagicMock(return_value=model)
    monkeypatch.setattr(answers, 'build_llm', build)
    return invoke


@pytest.mark.asyncio
@pytest.mark.parametrize('instruction,reason', [
    ('Click Continue', 'Navigation only; no applicant claim.'),
    ('Upload the supplied resume', 'File upload only.'),
    ('Choose Yes for US work authorization', 'Owner states US citizenship and authorization.'),
])
async def test_supported_answer_or_navigation_is_allowed(monkeypatch, instruction, reason):
    invoke = checker(monkeypatch, answers.AnswerCheck(reason=reason, supported=True, question=''))
    facts = json.dumps({'profile': {'name': 'Applicant'}, 'resume': 'Software Engineer'})
    assert await answers.check_application_answer(instruction, facts, 'US citizen; authorized to work in the US.') is None
    payload = json.loads(invoke.await_args.args[0][1].content)
    assert payload['instruction'] == instruction
    assert payload['applicant_facts'] == facts
    assert payload['application_rules'] == 'US citizen; authorized to work in the US.'


@pytest.mark.asyncio
@pytest.mark.parametrize('question', [
    'Do you hold citizenship in another country?',
    'Have you ever worked for a government entity?',
    'Does your current employer do business with ServiceNow?',
])
async def test_unknown_negative_answer_is_parked_with_exact_question(monkeypatch, question):
    checker(monkeypatch, answers.AnswerCheck(reason='No explicit supporting fact.', supported=False, question=question))
    with pytest.raises(ApplicationParked) as stopped:
        await answers.check_application_answer(f'Choose No for "{question}"', '{"resume":"Software engineer"}', 'US citizen')
    assert stopped.value.question == question


@pytest.mark.asyncio
async def test_final_review_passes_prefilled_answers_to_grounding_check(monkeypatch):
    question = 'Have you ever worked for a government entity?'
    invoke = checker(monkeypatch, answers.AnswerCheck(reason='Prefilled No lacks evidence.', supported=False, question=question))
    review = f'Review application\n{question}\nNo\nSubmit application'
    with pytest.raises(ApplicationParked, match='government entity'):
        await answers.check_application_answer('Submit application', '{}', 'US citizen', review_text=review)
    payload = json.loads(invoke.await_args.args[0][1].content)
    assert payload['review_text'] == review
    assert payload['mode'] == 'final_review'


@pytest.mark.asyncio
async def test_option_answer_audit_receives_parent_question_and_parks_it(monkeypatch):
    """Exercise the real applier/checker boundary with only the provider mocked."""
    from types import SimpleNamespace
    from backend.browser.tools.appliers.indeed import IndeedApplier

    question = ('Were you previously employed at HubSpot Inc or any of its subsidiaries? '
                'If Yes, please select which entity below.')
    option = 'No - Never been employed by Hubspot or a subsidiary'
    tree = f'[1-1] combobox: {question}\n  [1-2] option: {option}'
    native_page = MagicMock()
    native_page.snapshot = AsyncMock(return_value=SimpleNamespace(formatted_tree=tree))
    native_page.url = AsyncMock(return_value='https://smartapply.indeed.com/form/questions')
    agent = MagicMock()
    agent.browser.context.active_page = AsyncMock(return_value=native_page)
    invoke = checker(monkeypatch, None)

    async def reject_unknown(messages):
        payload = json.loads(messages[1].content)
        # Without the native field context, the checker sees only the option.
        visible_question = question if question in payload.get('page_text', '') else option
        return answers.AnswerCheck(supported=False, question=visible_question,
                                   reason='Prior employment is not established by the resume.')

    invoke.side_effect = reject_unknown
    applier = IndeedApplier(MagicMock(), 'fixture-session', stagehand=agent)
    with pytest.raises(ApplicationParked) as stopped:
        await applier._check_answer(f'Click {option}', '{"resume":"Software engineer"}')
    assert stopped.value.question == question
    payload = json.loads(invoke.await_args.args[0][1].content)
    assert payload['mode'] == 'next_action'
    assert payload['review_text'] == ''
    assert payload['page_text'] == tree
    assert 'Software engineer' in payload['applicant_facts']
    native_page.snapshot.assert_awaited_once_with(include_iframes=True)
    native_page.locator.assert_not_called()


@pytest.mark.asyncio
async def test_missing_next_action_snapshot_fails_closed_before_model_or_action(monkeypatch):
    from backend.browser.tools.appliers.indeed import IndeedApplier
    invoke = checker(monkeypatch, answers.AnswerCheck(supported=True, question='', reason='Allowed'))
    applier = IndeedApplier(MagicMock(), 'fixture-session', stagehand=MagicMock())
    monkeypatch.setattr(applier, '_visible_application_snapshot',
                        AsyncMock(side_effect=RuntimeError('Unreadable form')))
    with pytest.raises(RuntimeError, match='Unreadable form'):
        await applier._check_answer('Choose No', '{}')
    invoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_checker_failure_never_allows_action(monkeypatch):
    invoke = checker(monkeypatch, None)
    invoke.side_effect = RuntimeError('provider unavailable')
    with pytest.raises(RuntimeError, match='provider unavailable'):
        await answers.check_application_answer('Choose No', '{}', '')


@pytest.mark.asyncio
async def test_unsupported_check_without_question_fails_closed_without_inventing_one(monkeypatch):
    checker(monkeypatch, answers.AnswerCheck(reason='Unsupported.', supported=False, question=''))
    with pytest.raises(ValueError, match='question'):
        await answers.check_application_answer('Choose No', '{}', '')


@pytest.mark.asyncio
@pytest.mark.parametrize('question,answer,resume', [
    ('Do you have Anthropic experience?', 'Yes', 'Built an application using Anthropic APIs.'),
    ('Do you have at least three years of software engineering experience?', 'Yes', 'Software Engineer, January 2020 - December 2023.'),
])
async def test_resume_synthesis_returns_source_evidence(monkeypatch, question, answer, resume):
    invoke = checker(monkeypatch, answers.AnswerSuggestion(supported=True, answer=answer,
        reason='The quoted work supports the requested experience.',
        evidence=[answers.AnswerEvidence(source='resume', quote=resume)]))
    result = await answers.resolve_application_question(question, json.dumps({'resume': resume}), '')
    assert result.answer == answer
    assert result.evidence[0].quote == resume
    payload = json.loads(invoke.await_args.args[0][1].content)
    assert payload['question'] == question
    policy = invoke.await_args.args[0][0].content
    assert 'never\nsum overlapping periods' in policy
    assert 'formal certification' in policy


@pytest.mark.asyncio
async def test_experience_without_certification_remains_unknown(monkeypatch):
    checker(monkeypatch, answers.AnswerSuggestion(supported=False, answer='',
        reason='API usage supports experience but does not establish certification.'))
    assert await answers.resolve_application_question('Do you have an Anthropic certification?',
        '{"resume":"Built applications using Anthropic APIs."}', '') is None


@pytest.mark.asyncio
async def test_explicit_no_certification_rule_can_correct_prefilled_yes(monkeypatch):
    rule = 'I have Anthropic experience but no formal Anthropic certification; answer No to the combined question.'
    checker(monkeypatch, answers.AnswerSuggestion(supported=True, answer='No', reason='Explicit owner rule.',
        evidence=[answers.AnswerEvidence(source='application_rules', quote=rule)]))
    result = await answers.resolve_application_question('Do you possess Anthropic Experience and Certifications?', '{}', rule)
    assert result.answer == 'No'


@pytest.mark.asyncio
@pytest.mark.parametrize('evidence', [[], [answers.AnswerEvidence(source='resume', quote='Anthropic certified')]])
async def test_suggested_answer_cannot_use_missing_or_fabricated_evidence(monkeypatch, evidence):
    checker(monkeypatch, answers.AnswerSuggestion(supported=True, answer='Yes', reason='Claimed evidence.', evidence=evidence))
    with pytest.raises(ValueError, match='evidence'):
        await answers.resolve_application_question('Are you certified?', '{"resume":"Anthropic API project"}', '')
