"""Owner's application rules: prompt injection, parking, storage routes."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.browser.tools import form_filler
from backend.browser.tools.appliers import dispatcher
from backend.browser.tools.appliers.base import BaseApplier
from backend.browser.tools.appliers.generic import GenericApplier
from backend.gateway.routes import auth as auth_routes
from backend.orchestrator.agents import scoring
from backend.shared.application_rules import (
    MAX_RULES_CHARS,
    RULES_CLOSE,
    RULES_OPEN,
    ApplicationParked,
    format_rules_block,
    load_application_rules,
)
from backend.shared.models.schemas import ApplicationStatus, ATSType, JobBoard, JobListing

RULES = (
    "Eligibility: remote US only, senior+, Python stack, base >= $180k.\n"
    "Standard answers: sponsorship = No.\n"
    "Park: any question aimed at AI tools, own-voice essays, no-AI attestations."
)


def _job(job_id: str = "j1") -> JobListing:
    return JobListing(
        id=job_id,
        title="Senior Backend Engineer",
        company="Acme",
        location="Remote",
        url=f"https://boards.greenhouse.io/acme/jobs/{job_id}",
        board=JobBoard.GOOGLE_JOBS,
        ats_type=ATSType.GREENHOUSE,
        discovered_at=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# format_rules_block
# ---------------------------------------------------------------------------


def test_format_rules_block_empty_returns_empty():
    assert format_rules_block("", "scoring") == ""
    assert format_rules_block(None, "form") == ""
    assert format_rules_block("   \n", "form") == ""


def test_format_rules_block_delimits_text_and_adds_purpose_instructions():
    scoring_block = format_rules_block(RULES, "scoring")
    form_block = format_rules_block(RULES, "form")

    for block in (scoring_block, form_block):
        assert block.startswith("## Owner's application rules")
        assert f"{RULES_OPEN}\n{RULES}\n{RULES_CLOSE}" in block
        assert "Never invent facts" in block or "NEVER INVENT FACTS" in block

    assert "overall score MUST be 20 or lower" in scoring_block
    assert "park_question" not in scoring_block
    assert "PARK CONDITIONS" in form_block
    assert "park_question" in form_block


def test_format_rules_block_truncates_oversized_rules():
    block = format_rules_block("x" * (MAX_RULES_CHARS + 50), "form")
    inner = block.split(RULES_OPEN + "\n", 1)[1].split("\n" + RULES_CLOSE, 1)[0]
    assert inner == "x" * MAX_RULES_CHARS


def test_load_application_rules_skips_anonymous_users():
    with patch("backend.shared.billing_store.get_application_rules") as get_rules:
        assert load_application_rules("") == ""
        assert load_application_rules(None) == ""
        assert load_application_rules("unknown") == ""
        get_rules.assert_not_called()


def test_load_application_rules_reads_store():
    with patch("backend.shared.billing_store.get_application_rules", return_value=RULES) as get_rules:
        assert load_application_rules("user-1") == RULES
        get_rules.assert_called_once_with("user-1")


# ---------------------------------------------------------------------------
# form filler
# ---------------------------------------------------------------------------

_FIELDS = [
    {"selector": "#first_name", "label": "First name", "type": "text", "required": True},
    {
        "selector": "#q_ai",
        "label": "Are you using an AI tool or agent to complete this application?",
        "type": "text",
        "required": True,
    },
]


class _FakeStructuredLLM:
    def with_structured_output(self, _schema):
        return self


def _patch_llm(monkeypatch, result: form_filler.FormAnalysisResult):
    captured: dict = {}

    async def fake_invoke(_llm, messages, **_kwargs):
        captured["messages"] = messages
        return result

    monkeypatch.setattr(form_filler, "build_llm", lambda **_: _FakeStructuredLLM())
    monkeypatch.setattr(form_filler, "invoke_with_retry", fake_invoke)
    return captured


@pytest.mark.asyncio
async def test_analyse_form_without_rules_keeps_prompt_unchanged(monkeypatch):
    captured = _patch_llm(monkeypatch, form_filler.FormAnalysisResult(instructions=[
        form_filler.FillInstruction(selector="#first_name", action="fill", value="Ada"),
    ]))

    instructions = await form_filler.analyse_form(_FIELDS, "Ada Lovelace", "", user_profile={})

    assert captured["messages"][0].content == form_filler.FORM_ANALYSIS_PROMPT
    assert any(i["selector"] == "#first_name" and i["value"] == "Ada" for i in instructions)


@pytest.mark.asyncio
async def test_analyse_form_appends_rules_block_to_system_prompt(monkeypatch):
    captured = _patch_llm(monkeypatch, form_filler.FormAnalysisResult(instructions=[]))

    await form_filler.analyse_form(_FIELDS, "Ada", "", user_profile={}, application_rules=RULES)

    system = captured["messages"][0].content
    assert system.startswith(form_filler.FORM_ANALYSIS_PROMPT)
    assert RULES_OPEN in system and RULES_CLOSE in system and RULES in system


@pytest.mark.asyncio
async def test_analyse_form_raises_parked_with_exact_question(monkeypatch):
    question = _FIELDS[1]["label"]
    _patch_llm(monkeypatch, form_filler.FormAnalysisResult(
        instructions=[], park_question=f"  {question}\n",
    ))

    with pytest.raises(ApplicationParked) as excinfo:
        await form_filler.analyse_form(_FIELDS, "Ada", "", user_profile={}, application_rules=RULES)

    assert excinfo.value.question == question


@pytest.mark.asyncio
async def test_analyse_form_ignores_park_without_rules(monkeypatch):
    _patch_llm(monkeypatch, form_filler.FormAnalysisResult(
        instructions=[form_filler.FillInstruction(selector="#first_name", action="fill", value="Ada")],
        park_question="Are you a robot?",
    ))

    instructions = await form_filler.analyse_form(_FIELDS, "Ada", "", user_profile={})

    assert any(i["selector"] == "#first_name" for i in instructions)


# ---------------------------------------------------------------------------
# appliers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_base_applier_turns_parked_into_skipped_result(monkeypatch):
    question = "Please confirm you wrote these answers yourself without AI assistance."

    class _ParkingApplier(BaseApplier):
        PLATFORM = "test"

        async def apply(self, job, user_profile, resume_text, cover_letter, resume_file_path=None):
            raise ApplicationParked(question)

    emitted: list = []

    async def fake_emit(_session, event, payload):
        emitted.append((event, payload))

    monkeypatch.setattr("backend.browser.tools.appliers.base.emit_agent_event", fake_emit)

    applier = _ParkingApplier(page=MagicMock(), session_id="s1", application_rules=RULES)
    result = await applier.run(job=_job(), user_profile={}, resume_text="", cover_letter="")

    assert result.status == ApplicationStatus.SKIPPED
    assert result.error_message == question
    assert any(ev == "application_progress" and "Parked" in p["step"] for ev, p in emitted)


@pytest.mark.asyncio
async def test_generic_applier_lets_parked_escape_its_catch_all(monkeypatch):
    """The concrete appliers wrap apply() in `except Exception`; parking must escape it."""
    question = "Describe, in your own words, why you want this role."

    async def fake_analyse(**kwargs):
        assert kwargs["application_rules"] == RULES
        raise ApplicationParked(question)

    monkeypatch.setattr("backend.browser.tools.appliers.base.extract_form_fields", AsyncMock(return_value=_FIELDS))
    monkeypatch.setattr("backend.browser.tools.appliers.base.analyse_form", fake_analyse)
    monkeypatch.setattr("backend.browser.tools.appliers.base.emit_agent_event", AsyncMock())

    page = MagicMock()
    page.query_selector = AsyncMock(return_value=MagicMock())  # a <form> exists

    applier = GenericApplier(page, "s1", application_rules=RULES)
    result = await applier.run(job=_job(), user_profile={}, resume_text="", cover_letter="")

    assert result.status == ApplicationStatus.SKIPPED
    assert result.error_message == question


@pytest.mark.asyncio
async def test_dispatcher_forwards_rules_to_applier(monkeypatch):
    from backend.shared.config import settings
    monkeypatch.setattr(settings, "INDEED_EASY_APPLY_ONLY", False)
    seen: dict = {}

    class _Spy(BaseApplier):
        PLATFORM = "spy"

        def __init__(self, page, session_id, application_rules=""):
            super().__init__(page, session_id, application_rules=application_rules)
            seen["rules"] = application_rules

        async def apply(self, job, user_profile, resume_text, cover_letter, resume_file_path=None):
            return self._make_result(str(job.id), ApplicationStatus.SUBMITTED)

    monkeypatch.setattr(dispatcher, "_APPLIER_MAP", {ATSType.GREENHOUSE: _Spy})
    page = MagicMock()
    page.url = "https://boards.greenhouse.io/acme/jobs/1"

    result = await dispatcher.apply_with_playwright(
        job=_job(), user_profile={}, resume_text="", cover_letter="",
        resume_file_path=None, session_id="s1", page=page, application_rules=RULES,
    )

    assert result.status == ApplicationStatus.SUBMITTED
    assert seen["rules"] == RULES


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scoring_prompt_includes_owner_rules(monkeypatch):
    prompts: list[str] = []

    async def fake_invoke(_llm, messages, **_kwargs):
        prompts.append(messages[-1].content)
        return scoring.ScoringBatchResult(scores=[{
            "job_id": "j1", "score": 15,
            "score_breakdown": {"keyword_match": 10, "location_match": 0, "salary_match": 50, "experience_match": 40},
            "reasons": ["Fails rule: on-site in NYC", "Pay below floor"],
        }])

    monkeypatch.setattr(scoring, "build_llm", lambda **_: _FakeStructuredLLM())
    monkeypatch.setattr(scoring, "invoke_with_retry", fake_invoke)
    monkeypatch.setattr(scoring, "emit_agent_event", AsyncMock())
    monkeypatch.setattr(scoring, "get_active_prompt", lambda _key: None)
    monkeypatch.setattr("backend.shared.application_store.get_previously_applied_urls", lambda _u: set())
    monkeypatch.setattr("backend.shared.application_store.get_rate_limited_companies", lambda _u: set())
    monkeypatch.setattr("backend.shared.billing_store.get_blocked_companies", lambda _u: set())
    monkeypatch.setattr("backend.shared.billing_store.get_user_by_id", lambda _u: {"blocked_companies": []})
    monkeypatch.setattr("backend.shared.billing_store.get_application_rules", lambda _u: RULES)

    result = await scoring.run_scoring_agent({
        "session_id": "rules-test",
        "user_id": "user-1",
        "resume_text": "Python backend engineer",
        "discovered_jobs": [_job("j1")],
    })

    # The model honoured the rules with a 15, which the strictness floor
    # (min 30) then drops from the shortlist.
    assert result["scored_jobs"] == []
    assert len(prompts) == 1
    prompt = prompts[0]
    assert f"{RULES_OPEN}\n{RULES}\n{RULES_CLOSE}" in prompt
    assert prompt.index(RULES_CLOSE) < prompt.index("## Job Listings")


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_application_rules_routes_read_and_write(monkeypatch):
    monkeypatch.setattr(auth_routes, "get_current_user", lambda _req: {"id": "user-1"})
    store: dict = {"user-1": ""}
    monkeypatch.setattr("backend.shared.billing_store.get_application_rules", lambda uid: store[uid])
    monkeypatch.setattr(
        "backend.shared.billing_store.update_application_rules",
        lambda uid, rules: store.__setitem__(uid, rules),
    )

    assert await auth_routes.get_application_rules(MagicMock()) == {"application_rules": ""}

    body = auth_routes.ApplicationRulesUpdate(application_rules=f"  {RULES}\n\n")
    assert await auth_routes.update_application_rules(MagicMock(), body) == {"application_rules": RULES}
    assert store["user-1"] == RULES
    assert await auth_routes.get_application_rules(MagicMock()) == {"application_rules": RULES}


@pytest.mark.asyncio
async def test_application_rules_route_rejects_oversized_text(monkeypatch):
    monkeypatch.setattr(auth_routes, "get_current_user", lambda _req: {"id": "user-1"})
    update = MagicMock()
    monkeypatch.setattr("backend.shared.billing_store.update_application_rules", update)

    body = auth_routes.ApplicationRulesUpdate(application_rules="x" * (MAX_RULES_CHARS + 1))
    response = await auth_routes.update_application_rules(MagicMock(), body)

    assert response.status_code == 400
    update.assert_not_called()
