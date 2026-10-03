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
