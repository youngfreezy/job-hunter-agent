from datetime import datetime

import pytest

from backend.browser.tools.job_boards import RankedListingIndices, rank_by_relevance
from backend.shared.models.schemas import ATSType, JobBoard, JobListing


class _FakeLLM:
    def with_structured_output(self, _schema):
        return self


def _job(job_id: str, title: str, company: str, snippet: str = "") -> JobListing:
    return JobListing(
        id=job_id,
        title=title,
        company=company,
        location="Remote",
        url=f"https://example.com/{job_id}",
        board=JobBoard.LINKEDIN,
        ats_type=ATSType.UNKNOWN,
        description_snippet=snippet,
        discovered_at=datetime.utcnow(),
    )


@pytest.mark.asyncio
async def test_rank_by_relevance_uses_structured_output(monkeypatch):
    async def fake_invoke(_llm, _messages, *, max_retries=0):
        return RankedListingIndices(indices=[2, 0, 1])

    monkeypatch.setattr("backend.shared.llm.build_llm", lambda **_: _FakeLLM())
    monkeypatch.setattr("backend.shared.llm.invoke_with_retry", fake_invoke)

    listings = [
        _job("1", "Frontend Engineer", "A"),
        _job("2", "Platform Engineer", "B"),
        _job("3", "Senior AI Engineer", "C"),
    ]

    ranked = await rank_by_relevance(listings, ["AI", "Python"], limit=2)

    assert [job.id for job in ranked] == ["3", "1"]


@pytest.mark.asyncio
async def test_rank_by_relevance_falls_back_to_keyword_sort(monkeypatch):
    async def fake_invoke(_llm, _messages, *, max_retries=0):
        raise RuntimeError("structured output failed")

    monkeypatch.setattr("backend.shared.llm.build_llm", lambda **_: _FakeLLM())
    monkeypatch.setattr("backend.shared.llm.invoke_with_retry", fake_invoke)

    listings = [
        _job("1", "Frontend Engineer", "A", "React only"),
        _job("2", "Senior AI Engineer", "B", "Python LLM LangGraph"),
        _job("3", "Backend Engineer", "C", "Python APIs"),
    ]

    ranked = await rank_by_relevance(listings, ["Python", "LLM", "LangGraph"], limit=2)

    assert [job.id for job in ranked] == ["2", "3"]
