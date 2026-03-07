import pytest

from backend.orchestrator.agents.steering_judge import SteeringDirective, SteeringJudgeResult
from backend.orchestrator.agents.workflow_supervisor import run_workflow_supervisor


@pytest.mark.asyncio
async def test_workflow_supervisor_sets_pause_and_skip(monkeypatch):
    async def fake_judge(**_kwargs):
        return SteeringJudgeResult(
            response_message="I'll pause the workflow.",
            directives=[
                SteeringDirective(action="pause", reason="user asked"),
                SteeringDirective(action="skip_next_job", reason="user asked"),
            ],
        )

    emitted = []

    async def fake_emit(session_id, event_type, payload):
        emitted.append((session_id, event_type, payload))

    monkeypatch.setattr(
        "backend.orchestrator.agents.workflow_supervisor.judge_steering",
        fake_judge,
    )
    monkeypatch.setattr(
        "backend.orchestrator.agents.workflow_supervisor.emit_agent_event",
        fake_emit,
    )

    state = {
        "session_id": "sess-1",
        "status": "applying",
        "keywords": ["Python"],
        "locations": ["Remote"],
        "human_messages": ["pause and skip the next job"],
        "steering_messages_processed": 0,
        "applications_submitted": [],
        "applications_failed": [],
        "applications_skipped": [],
        "agent_statuses": {},
        "errors": [],
    }

    updates = await run_workflow_supervisor(state, continue_to="application")

    assert updates["pause_requested"] is True
    assert updates["skip_next_job_requested"] is True
    assert updates["pause_resume_node"] == "application"
    assert updates["status"] == "paused"
    assert updates["steering_messages_processed"] == 1
    assert emitted and emitted[0][0] == "sess-1"


@pytest.mark.asyncio
async def test_workflow_supervisor_noop_without_new_messages(monkeypatch):
    async def fake_judge(**_kwargs):
        raise AssertionError("judge should not run")

    monkeypatch.setattr(
        "backend.orchestrator.agents.workflow_supervisor.judge_steering",
        fake_judge,
    )

    updates = await run_workflow_supervisor(
        {
            "session_id": "sess-2",
            "human_messages": ["already handled"],
            "steering_messages_processed": 1,
        },
        continue_to="reporting",
    )

    assert updates == {}
