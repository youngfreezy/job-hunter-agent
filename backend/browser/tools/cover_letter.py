"""Cover Letter Generator -- creates job-specific cover letters using Claude.

Produces a tailored cover letter based on the user's coached resume,
the specific job listing details, and the cover letter template from
the Career Coach agent.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from backend.shared.llm import build_llm, invoke_with_retry, light_model
from backend.shared.models.schemas import CoverLetter, JobListing

logger = logging.getLogger(__name__)

COVER_LETTER_SYSTEM = """\
You are an expert career counselor writing a cover letter for a job application.

Given the applicant's resume, a cover letter template, and a specific job listing,
write a personalised cover letter that:

1. Opens with a compelling hook referencing the specific company and role
2. Highlights 2-3 key qualifications from the resume that match the job
3. Demonstrates knowledge of the company (infer from the job description)
4. Shows enthusiasm and cultural fit
5. Closes with a confident call to action

Keep it concise: 3-4 paragraphs, under 400 words.

Return ONLY the cover letter text. No JSON, no markdown fences, no commentary.
"""


async def generate_cover_letter(
    job: JobListing,
    resume_text: str,
    template: Optional[str] = None,
    tone: str = "professional",
) -> CoverLetter:
    """Generate a tailored cover letter for a specific job.

    Parameters
    ----------
    job:
        The job listing to write the cover letter for.
    resume_text:
        The applicant's resume (coached or original).
    template:
        Optional cover letter template from the Career Coach agent.
    tone:
        Tone for the letter (professional, casual, enthusiastic).

    Returns
    -------
    CoverLetter
    """
    llm = build_llm(model=light_model(), max_tokens=2048, temperature=0.7)

    user_content = (
        f"## Job Details\n"
        f"- Title: {job.title}\n"
        f"- Company: {job.company}\n"
        f"- Location: {job.location}\n"
        f"- Description: {job.description_snippet or 'Not available'}\n\n"
        f"## Resume\n{resume_text[:3000]}\n\n"
    )
    if template:
        user_content += f"## Cover Letter Template\n{template[:2000]}\n\n"
    user_content += f"## Tone: {tone}\n"

    response = await invoke_with_retry(llm, [
        SystemMessage(content=COVER_LETTER_SYSTEM),
        HumanMessage(content=user_content),
    ])

    text = response.content
    if isinstance(text, list):
        text = "".join(
            block if isinstance(block, str) else block.get("text", "")
            for block in text
        )

    logger.info(
        "Generated cover letter for %s at %s (%d chars)",
        job.title, job.company, len(text),
    )

    return CoverLetter(
        job_id=job.id,
        text=text.strip(),
        tone=tone,
    )
