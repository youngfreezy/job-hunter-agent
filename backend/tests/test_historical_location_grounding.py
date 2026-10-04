"""Contact-location transfer is rejected even when the model says supported."""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.browser import application_answers as answers
from backend.browser.tools.appliers.indeed import IndeedApplier
from backend.shared.application_rules import ApplicationParked

RESUME = ('San Francisco, CA / Dallas, TX (Remote)\n\n'
          'AI Fellow | Example Labs | July 2026 - Present\nBuilt AI systems.\n\n'
          'Senior Engineer | Prior Systems | January 2020 - June 2026\nBuilt APIs.')
CONTEXT = ('Work experience\nJob title: AI Fellow\nEmployer: Example Labs\n'
           'City, state: San Francisco, CA\nSave\nContinue')
QUESTION = 'City, state — AI Fellow at Example Labs'


def model(monkeypatch, result):
    invoke = AsyncMock(return_value=result)
    llm = MagicMock(); llm.with_structured_output.return_value.ainvoke = invoke
    monkeypatch.setattr(answers, 'build_llm', MagicMock(return_value=llm))
    return invoke


def location(quote, source='resume', employer='Example Labs', role='AI Fellow'):
    return answers.HistoricalLocation(question=QUESTION, employer=employer, role=role,
        location='San Francisco, CA', evidence=[answers.AnswerEvidence(source=source, quote=quote)])


@pytest.mark.asyncio
@pytest.mark.parametrize('instruction,review', [
    ('Fill City, state with San Francisco, CA', False),
    ('Click the San Francisco, CA option', False),
    ('Click Save', False), ('Click Continue', False), ('Submit application', True),
])
async def test_real_applier_gate_rejects_header_transfer_before_action(monkeypatch, instruction, review):
    model(monkeypatch, answers.AnswerCheck(supported=True, question='', reason='Applicant lives there.',
        historical_locations=[location('San Francisco, CA / Dallas, TX (Remote)')]))
    applier = IndeedApplier(MagicMock(), 'offline', stagehand=MagicMock())
    monkeypatch.setattr(applier, '_visible_application_snapshot', AsyncMock(return_value={'text': CONTEXT}))
    with pytest.raises(ApplicationParked, match='AI Fellow at Example Labs'):
        await applier._check_answer(instruction, json.dumps({'resume': RESUME}), review=review)


@pytest.mark.asyncio
async def test_model_cannot_omit_scoped_evidence_on_history_city_form(monkeypatch):
    invoke = model(monkeypatch, answers.AnswerCheck(supported=True, question='', reason='Navigation only'))
    with pytest.raises(ApplicationParked, match='City, state'):
        await answers.check_application_answer('Continue', json.dumps({'resume': RESUME}), '', page_text=CONTEXT)
    assert json.loads(invoke.await_args.args[0][1].content)['historical_location_evidence_required'] is True


@pytest.mark.asyncio
@pytest.mark.parametrize('quote', [RESUME, RESUME.replace('\n', ' '),
    'San Francisco, CA / Dallas, TX (Remote)\n\nAI Fellow | Example Labs | July 2026 - Present'])
async def test_wide_or_flattened_quotes_cannot_join_header_to_record(monkeypatch, quote):
    model(monkeypatch, answers.AnswerCheck(supported=True, question='', reason='Quoted source',
        historical_locations=[location(quote)]))
    with pytest.raises(ApplicationParked):
        await answers.check_application_answer('Fill City, state', json.dumps({'resume': RESUME}), '', page_text=CONTEXT)


@pytest.mark.asyncio
async def test_flat_profile_cannot_join_contact_city_to_job(monkeypatch):
    profile = {'location': 'San Francisco, CA', 'employer': 'Example Labs', 'title': 'AI Fellow'}
    model(monkeypatch, answers.AnswerCheck(supported=True, question='', reason='Profile says so',
        historical_locations=[location(json.dumps(profile), source='profile')]))
    with pytest.raises(ApplicationParked):
        await answers.check_application_answer('Fill City, state', json.dumps({'profile': profile}), '', page_text=CONTEXT)


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', [
    'AI Fellow | Example Labs | San Francisco, CA',
    'AI Fellow | Example Labs\nSan Francisco, CA',
])
async def test_employer_role_location_entry_supports_answer_across_pdf_lines(monkeypatch, entry):
    model(monkeypatch, answers.AnswerCheck(supported=True, question='', reason='Same role entry',
        historical_locations=[location(entry)]))
    await answers.check_application_answer('Fill City, state', json.dumps({'resume': entry}), '', page_text=CONTEXT)


@pytest.mark.asyncio
async def test_explicit_scoped_owner_answer_is_supported(monkeypatch):
    rule = json.dumps({'company': 'Hiring Company', 'question': QUESTION, 'answer': 'San Francisco, CA'})
    model(monkeypatch, answers.AnswerCheck(supported=True, question='', reason='Owner confirmed',
        historical_locations=[location(rule, source='application_rules')]))
    await answers.check_application_answer('Fill City, state', json.dumps({'resume': RESUME}), rule, page_text=CONTEXT)


@pytest.mark.asyncio
async def test_other_employer_city_is_not_current_record_evidence(monkeypatch):
    quote = 'Senior Engineer | Prior Systems | San Francisco, CA'
    model(monkeypatch, answers.AnswerCheck(supported=True, question='', reason='Wrong role',
        historical_locations=[location(quote, employer='Prior Systems', role='Senior Engineer')]))
    with pytest.raises(ApplicationParked):
        await answers.check_application_answer('Fill City, state', json.dumps({'resume': quote}), '', page_text=CONTEXT)


@pytest.mark.asyncio
async def test_parked_question_resolver_cannot_promote_contact_location(monkeypatch):
    header = 'San Francisco, CA / Dallas, TX (Remote)'
    model(monkeypatch, answers.AnswerSuggestion(supported=True, answer='San Francisco, CA', reason='Lives there',
        evidence=[answers.AnswerEvidence(source='resume', quote=header)],
        historical_locations=[location(header)]))
    with pytest.raises(ApplicationParked):
        await answers.resolve_application_question('Work experience: ' + QUESTION, json.dumps({'resume': RESUME}), '')


@pytest.mark.asyncio
async def test_contact_location_question_still_uses_contact_evidence(monkeypatch):
    model(monkeypatch, answers.AnswerCheck(supported=True, question='', reason='Contact header'))
    await answers.check_application_answer('Fill City, state', json.dumps({'resume': RESUME}), '',
                                           page_text='Contact information\nCity, state')


@pytest.mark.asyncio
async def test_contact_city_with_employment_footer_is_not_history(monkeypatch):
    model(monkeypatch, answers.AnswerCheck(supported=True, question='', reason='Contact address'))
    await answers.check_application_answer('Fill City, state', json.dumps({'resume': RESUME}), '',
        page_text='Contact information\nCity, state\nEqual employment opportunity employer')


@pytest.mark.asyncio
@pytest.mark.parametrize('quote', [
    'AI Fellow | Example Labs\nSenior Engineer | Prior Systems | San Francisco, CA',
    'AI Fellow | Example Labs\nAI Fellow | Other Labs | San Francisco, CA',
])
async def test_adjacent_other_record_cannot_lend_its_city(monkeypatch, quote):
    model(monkeypatch, answers.AnswerCheck(supported=True, question='', reason='Wrong record relation',
        historical_locations=[location(quote)]))
    with pytest.raises(ApplicationParked):
        await answers.check_application_answer('Continue', json.dumps({'resume': quote}), '', page_text=CONTEXT)


@pytest.mark.asyncio
async def test_other_saved_question_answer_cannot_lend_its_city(monkeypatch):
    rules = (json.dumps({'question': QUESTION, 'answer': 'Unknown'}) + '\n' +
             json.dumps({'question': 'City, state for Senior Engineer at Prior Systems', 'answer': 'San Francisco, CA'}))
    model(monkeypatch, answers.AnswerCheck(supported=True, question='', reason='Joined two rules',
        historical_locations=[location(rules, source='application_rules')]))
    with pytest.raises(ApplicationParked):
        await answers.check_application_answer('Continue', '{}', rules, page_text=CONTEXT)


@pytest.mark.asyncio
async def test_duplicate_accessible_label_does_not_invent_another_history_record(monkeypatch):
    entry = 'AI Fellow | Example Labs | San Francisco, CA'
    model(monkeypatch, answers.AnswerCheck(supported=True, question='', reason='Same role',
        historical_locations=[location(entry)]))
    await answers.check_application_answer('Continue', json.dumps({'resume': entry}), '',
        page_text=CONTEXT + '\n[2] combobox: City, state: San Francisco, CA')


@pytest.mark.asyncio
async def test_final_review_checks_each_reported_prefilled_history_record(monkeypatch):
    entry = 'AI Fellow | Example Labs | San Francisco, CA'
    model(monkeypatch, answers.AnswerCheck(supported=True, question='', reason='First role known',
        historical_locations=[location(entry),
            location('San Francisco, CA / Dallas, TX (Remote)', employer='Prior Systems', role='Senior Engineer')]))
    with pytest.raises(ApplicationParked, match='Senior Engineer at Prior Systems'):
        await answers.check_application_answer('Submit', json.dumps({'resume': RESUME + '\n' + entry}), '',
            review_text=CONTEXT + '\nSenior Engineer at Prior Systems\nCity, state: San Francisco, CA')
