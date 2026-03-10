# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Resume analysis endpoint for Quick Start mode.

Extracts keywords, locations, and preferences from resume text using a fast
LLM call, so users can launch a session with minimal manual input.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.gateway.deps import get_current_user
from backend.shared.llm import build_llm, light_model, invoke_with_retry
from backend.shared.models.schemas import SearchConfig

from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/resume", tags=["resume"])

_ANALYZE_SYSTEM_PROMPT = """\
You are a resume analysis assistant. Given a resume, extract structured job \
search preferences the candidate would likely use.

**Instructions**
1. Extract 3-5 job title keywords the person is best suited for. Focus on \
   actual role titles (e.g. "Senior Data Engineer", "ML Platform Engineer"), \
   not generic skills.
2. Extract locations from the resume (city, state). If the resume mentions \
   "remote" or no clear location, return ["Remote"].
3. Estimate experience level: "entry", "mid", "senior", or "executive".
4. Suggest which job boards would be most relevant: choose from \
   "linkedin", "indeed", "glassdoor", "ziprecruiter".
5. If the resume strongly suggests remote work preference, set remote_only \
   to true.
"""


class ResumeAnalyzeRequest(BaseModel):
    resume_text: str


class ResumeAnalyzeResponse(BaseModel):
    keywords: List[str]
    locations: List[str]
    experience_level: Optional[str] = None
    suggested_job_boards: List[str] = ["linkedin", "indeed", "glassdoor", "ziprecruiter"]
    remote_likely: bool = False


@router.post("/analyze", response_model=ResumeAnalyzeResponse)
async def analyze_resume(body: ResumeAnalyzeRequest, request: Request):
    """Extract job search preferences from resume text using a fast LLM."""
    get_current_user(request)  # auth check

    resume_text = body.resume_text.strip()
    if not resume_text:
        raise HTTPException(status_code=400, detail="resume_text is required")

    if len(resume_text) < 50:
        raise HTTPException(status_code=400, detail="Resume text is too short to analyze")

    try:
        llm = build_llm(model=light_model(), max_tokens=4096, temperature=0.0)
        structured_llm = llm.with_structured_output(SearchConfig)

        messages = [
            SystemMessage(content=_ANALYZE_SYSTEM_PROMPT),
            HumanMessage(content=f"--- BEGIN RESUME ---\n{resume_text}\n--- END RESUME ---"),
        ]

        config: SearchConfig = await invoke_with_retry(structured_llm, messages)

        return ResumeAnalyzeResponse(
            keywords=config.keywords[:6],
            locations=config.locations if config.locations else ["Remote"],
            experience_level=config.experience_level,
            suggested_job_boards=["linkedin", "indeed", "glassdoor", "ziprecruiter"],
            remote_likely=config.remote_only,
        )

    except Exception as e:
        logger.exception("Resume analysis failed")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
