from datetime import datetime

import pytest

from backend.orchestrator.agents.scoring import ScoringBatchResult, run_scoring_agent
from backend.shared.models.schemas import ATSType, JobBoard, JobListing


class _FakeLLM:
    def with_structured_output(self, _schema):
        return self


def _job(job_id: str) -> JobListing:
    return JobListing(
        id=job_id,
        title=f"Backend Engineer {job_id}",
        company="Example",
        location="Remote",
        url=f"https://example.com/{job_id}",
        board=JobBoard.LINKEDIN,
        ats_type=ATSType.UNKNOWN,
        description_snippet="Python FastAPI AWS PostgreSQL Redis",
        discovered_at=datetime.utcnow(),
        is_remote=True,
    )


@pytest.mark.asyncio
async def test_scoring_agent_splits_batches_on_length_limit(monkeypatch):
    async def fake_emit(*_args, **_kwargs):
        return None

    async def fake_invoke(_llm, messages, *, max_retries=0):
        prompt = messages[-1].content
        ids = []
        for line in prompt.splitlines():
            if line.startswith("- ID: "):
                ids.append(line.replace("- ID: ", "").strip())
        if len(ids) > 2:
            raise RuntimeError("length limit reached")
        return ScoringBatchResult(
            scores=[
                {
                    "job_id": job_id,
                    "score": 80,
                    "score_breakdown": {
                        "keyword_match": 85,
                        "location_match": 100,
                        "salary_match": 50,
                        "experience_match": 75,
                    },
                    "reasons": ["Strong backend overlap", "Remote fit"],
                }
                for job_id in ids
            ]
        )

    monkeypatch.setattr("backend.orchestrator.agents.scoring.build_llm", lambda **_: _FakeLLM())
    monkeypatch.setattr("backend.orchestrator.agents.scoring.invoke_with_retry", fake_invoke)
    monkeypatch.setattr("backend.orchestrator.agents.scoring.emit_agent_event", fake_emit)

    result = await run_scoring_agent(
        {
            "session_id": "score-split-test",
            "resume_text": "Python FastAPI backend engineer",
            "discovered_jobs": [_job(str(i)) for i in range(6)],
        }
    )

    assert result["status"] == "tailoring"
    assert len(result["scored_jobs"]) == 6
