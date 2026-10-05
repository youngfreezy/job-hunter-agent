"""The same application outcome has one meaning across browser batch sizes."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.orchestrator.agents import application
from backend.shared.config import settings
from backend.shared.models.schemas import ApplicationErrorCategory, ApplicationResult, ApplicationStatus, ATSType, JobBoard, JobListing


@pytest.mark.parametrize("message,category", [
    (None, None), ("Verification code required at login", ApplicationErrorCategory.TOTP_REQUIRED),
    ("Auth requires captcha", ApplicationErrorCategory.AUTH_REQUIRED),
    ("Job removed", ApplicationErrorCategory.JOB_EXPIRED), ("Captcha", ApplicationErrorCategory.CAPTCHA),
    ("Request timed out", ApplicationErrorCategory.TIMEOUT), ("Insufficient_credits", ApplicationErrorCategory.CREDIT_INSUFFICIENT),
    ("Already applied", ApplicationErrorCategory.DUPLICATE), ("Rate_limit", ApplicationErrorCategory.RATE_LIMITED),
    ("No_confirmation after submit", ApplicationErrorCategory.NO_CONFIRMATION),
    ("Submit button", ApplicationErrorCategory.SUBMIT_FAILED), ("Form field", ApplicationErrorCategory.FORM_FILL_ERROR),
    ("Selector missing", ApplicationErrorCategory.FORM_NAVIGATION), ("Unexpected problem", ApplicationErrorCategory.UNKNOWN),
])
def test_error_category_rule_order_is_preserved(message, category):
    assert application._infer_error_category(message) is category


@pytest.mark.parametrize("quick,threshold", [(False, 3), (True, 5)])
def test_fallback_systemic_streak_and_site_blocker_reset(quick, threshold):
    failure = ApplicationResult(job_id="job", status=ApplicationStatus.FAILED, error_message="Form fill failed")
    blocker = ApplicationResult(job_id="blocked", status=ApplicationStatus.FAILED, error_message="Job expired")
    assert application._hardcoded_fallback(failure, [failure] * threshold, 10, quick).decision is application.SupervisorDecision.PAUSE
    assert application._hardcoded_fallback(failure, [failure] * (threshold - 1), 10, quick).decision is application.SupervisorDecision.CONTINUE
    decision = application._hardcoded_fallback(blocker, [failure] * threshold + [blocker], 10, quick)
    assert decision.decision is application.SupervisorDecision.CONTINUE
    assert decision.is_systemic is False


@pytest.fixture
def batch_run(monkeypatch):
    monkeypatch.setattr(settings, "API_APPLY_ENABLED", False)
    monkeypatch.setattr(settings, "INDEED_ONLY", False)
    monkeypatch.setattr(settings, "INDEED_EASY_APPLY_ONLY", False)
    monkeypatch.setattr(settings, "SKYVERN_CONCURRENCY", 2)
    manager = MagicMock(stagehand=object(), live_view_url=None, browserbase_session_id=None)
    manager.start_for_task = AsyncMock()
    manager.new_context = AsyncMock(return_value=("context", object()))
    manager.stop = AsyncMock()
    monkeypatch.setattr(application, "BrowserManager", lambda: manager)
    monkeypatch.setattr(application, "emit_agent_event", AsyncMock())
    monkeypatch.setattr(application, "_db_record_result", MagicMock())
    monkeypatch.setattr("backend.moltbook.feedback_loop.record_application_result", MagicMock())
    monkeypatch.setattr("backend.shared.llm.build_llm", MagicMock(side_effect=RuntimeError("Offline test: model disabled")))
    jobs = [JobListing(id=f"job-{i}", title="Engineer", company=f"Company {i}",
                       location="Remote", url=f"https://careers.example.com/{i}", board=JobBoard.INDEED)
            for i in range(2)]

    async def run(first, count=1, *, api=False, second=None):
        if api:
            monkeypatch.setattr(settings, "API_APPLY_ENABLED", True)
            for job in jobs:
                job.ats_type = ATSType.GREENHOUSE
        responses = [first, second or ApplicationResult(job_id="job-1", status=ApplicationStatus.SUBMITTED)]
        async def apply(job_id, *args, **kwargs):
            result = responses[int(job_id[-1])]
            if isinstance(result, list):
                result = result.pop(0)
            if isinstance(result, BaseException):
                raise result
            return result
        monkeypatch.setattr(application, "_apply_to_job", AsyncMock(side_effect=apply))
        return await application.run_application_agent({"session_id": "test", "user_id": "owner",
            "application_queue": [j.id for j in jobs[:count]], "discovered_jobs": jobs[:count]})
    return run, manager


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 2])
async def test_every_failed_browser_result_reaches_supervisor(batch_run, monkeypatch, count):
    run, manager = batch_run
    supervisor = AsyncMock(return_value=application.ApplicationSupervisorResult(
        decision=application.SupervisorDecision.CONTINUE, reasoning="Site unavailable", is_systemic=False))
    monkeypatch.setattr(application, "_call_application_supervisor", supervisor)
    failure = ApplicationResult(job_id="job-0", status=ApplicationStatus.FAILED, error_message="Site unavailable")
    result = await run(failure, count)
    assert result["applications_failed"] == [failure]
    supervisor.assert_awaited_once()
    manager.stop.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 2])
@pytest.mark.parametrize("failure_step", ["model_budget", "duplicate_check"])
async def test_budget_and_history_stops_always_reach_existing_pause_interrupt(batch_run, count, failure_step):
    run, manager = batch_run
    result = await run(ApplicationResult(job_id="job-0", status=ApplicationStatus.FAILED, failure_step=failure_step), count)
    assert result["status"] == "paused"
    assert result["pause_requested"] is True
    assert result["pause_resume_node"] == "application"
    if count == 2:
        assert [r.job_id for r in result["applications_submitted"]] == ["job-1"]
    manager.stop.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 2])
async def test_missing_answer_is_visible_in_application_question_queue(batch_run, count):
    run, _ = batch_run
    result = await run(ApplicationResult(job_id="job-0", status=ApplicationStatus.SKIPPED,
        error_category=ApplicationErrorCategory.NEEDS_INPUT, error_message="What is your notice period?"), count)
    assert result["application_questions"]["job-0"]["question"] == "What is your notice period?"
    assert result["applications_skipped"] == ["job-0"]


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 2])
async def test_cancellation_propagates_after_browser_cleanup(batch_run, count):
    run, manager = batch_run
    with pytest.raises(asyncio.CancelledError):
        await run(asyncio.CancelledError(), count)
    manager.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_api_fallback_marks_api_failed_before_entering_browser(batch_run):
    run, manager = batch_run
    failed = ApplicationResult(job_id="job-0", status=ApplicationStatus.FAILED,
        error_category=ApplicationErrorCategory.FORM_FILL_ERROR)
    submitted = ApplicationResult(job_id="job-0", status=ApplicationStatus.SUBMITTED)
    result = await run([failed, submitted], api=True)
    assert result["applications_submitted"] == [submitted]
    assert "job-0" in application._apply_to_job.await_args.kwargs["state"]["api_failed_job_ids"]
    manager.start_for_task.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", [
    ApplicationResult(job_id="job-0", status=ApplicationStatus.FAILED,
                      error_category=ApplicationErrorCategory.SUBMISSION_UNCERTAIN),
    RuntimeError("Delivery could not be determined"),
])
async def test_unknown_api_delivery_never_starts_browser_fallback(batch_run, outcome):
    run, manager = batch_run
    result = await run(outcome, api=True)
    manager.start_for_task.assert_not_awaited()
    assert result["applications_failed"][0].error_category is ApplicationErrorCategory.SUBMISSION_UNCERTAIN


@pytest.mark.asyncio
async def test_cancelled_api_batch_does_not_start_a_browser(batch_run):
    run, manager = batch_run
    with pytest.raises(asyncio.CancelledError):
        await run(asyncio.CancelledError(), api=True)
    manager.start_for_task.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_step", ["model_budget", "duplicate_check"])
async def test_explicit_safety_stop_overrides_earlier_ordinary_batch_pause(batch_run, monkeypatch, failure_step):
    run, _ = batch_run
    real_supervisor = application._call_application_supervisor

    async def supervise(result, **kwargs):
        if result.failure_step:
            return await real_supervisor(result=result, **kwargs)
        return application.ApplicationSupervisorResult(
            decision=application.SupervisorDecision.PAUSE, reasoning="Review ordinary failure", is_systemic=True)

    monkeypatch.setattr(application, "_call_application_supervisor", AsyncMock(side_effect=supervise))
    result = await run(ApplicationResult(job_id="job-0", status=ApplicationStatus.FAILED), count=2,
        second=ApplicationResult(job_id="job-1", status=ApplicationStatus.FAILED, failure_step=failure_step))
    assert result["pause_requested"] is True
    assert result["pause_resume_node"] == "application"
    # All batch results are already available: skip even the ordinary
    # supervisor when a deterministic budget/history stop is known.
    assert [call.kwargs["result"].job_id for call in application._call_application_supervisor.await_args_list] == ["job-1"]
    from backend.shared.llm import build_llm
    build_llm.assert_not_called()
