# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Direct ATS API submission — bypasses browser automation entirely.

Generic dispatcher: try direct API submission first, return None if unsupported
or blocked (caller falls back to Skyvern).

Supported ATS platforms:
  - Greenhouse: POST multipart form to boards-api.greenhouse.io
  - Lever: POST multipart form to api.lever.co

Design: this module is intentionally stateless and reusable. Each ATS handler
is a pure async function that takes job data + user data → ApplicationResult.
New ATS backends can be added by implementing the same signature and registering
in _ATS_HANDLERS.
"""

from __future__ import annotations

import json
import logging
import re
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from backend.shared.config import get_settings
from backend.shared.llm import HAIKU_MODEL, build_llm, invoke_with_retry
from backend.shared.models.schemas import (
    ApplicationErrorCategory,
    ApplicationResult,
    ApplicationStatus,
    ATSType,
    JobListing,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# URL parsing helpers
# ---------------------------------------------------------------------------

_GREENHOUSE_URL_RE = re.compile(
    r"boards\.greenhouse\.io/([^/]+)/jobs/(\d+)", re.I
)
_LEVER_URL_RE = re.compile(
    r"jobs\.lever\.co/([^/]+)/([a-f0-9-]+)", re.I
)


def _parse_greenhouse_url(url: str) -> Optional[tuple[str, str]]:
    """Extract (board_token, job_id) from a Greenhouse URL."""
    m = _GREENHOUSE_URL_RE.search(url)
    if m:
        return m.group(1), m.group(2)
    return None


def _parse_lever_url(url: str) -> Optional[tuple[str, str]]:
    """Extract (company, posting_id) from a Lever URL."""
    m = _LEVER_URL_RE.search(url)
    if m:
        return m.group(1), m.group(2)
    return None


# ---------------------------------------------------------------------------
# Resume file helper
# ---------------------------------------------------------------------------

def _read_resume_bytes(resume_file_path: Optional[str]) -> Optional[tuple[bytes, str]]:
    """Read resume file, decrypting if needed. Returns (bytes, filename) or None."""
    if not resume_file_path:
        return None
    try:
        if resume_file_path.endswith(".enc"):
            from backend.shared.resume_crypto import decrypted_tempfile
            with decrypted_tempfile(resume_file_path) as tmp_path:
                with open(tmp_path, "rb") as f:
                    data = f.read()
                return data, "resume.pdf"
        else:
            with open(resume_file_path, "rb") as f:
                data = f.read()
            return data, resume_file_path.rsplit("/", 1)[-1]
    except Exception:
        logger.warning("Failed to read resume file %s", resume_file_path, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# LLM question answering (Greenhouse custom questions)
# ---------------------------------------------------------------------------

async def _answer_greenhouse_questions(
    questions: List[Dict],
    user_profile: Dict[str, str],
    resume_text: str,
    cover_letter: str,
    job_title: str,
    job_company: str,
) -> Dict[str, str]:
    """Use Claude Haiku to answer Greenhouse custom questions.

    Returns {f"question_{id}": answer_value} for each answerable question.
    """
    if not questions:
        return {}

    # Build a compact description of each question for the LLM
    q_descriptions = []
    for q in questions:
        q_id = q.get("id")
        label = q.get("label", "")
        required = q.get("required", False)
        fields = q.get("fields", [])
        if not fields or not q_id:
            continue

        field = fields[0]
        field_type = field.get("type", "")
        values = field.get("values", [])

        desc: Dict[str, Any] = {
            "id": q_id,
            "label": label,
            "required": required,
            "type": field_type,
        }
        if values:
            desc["options"] = [
                {"value": v.get("value"), "label": v.get("label")}
                for v in values[:20]  # Cap options to avoid token bloat
            ]
        q_descriptions.append(desc)

    if not q_descriptions:
        return {}

    from langchain_core.messages import HumanMessage, SystemMessage

    system_msg = SystemMessage(content=(
        "You are filling out a job application form. Answer each question based on "
        "the applicant's resume and cover letter. Be concise, professional, and truthful.\n\n"
        "Rules:\n"
        "- For select fields, you MUST return the exact 'value' from the options list\n"
        "- For text/textarea fields, write a brief, relevant answer\n"
        "- For yes/no questions about work authorization or relocation: answer 'Yes'\n"
        "- For sponsorship questions: answer 'No' (does not require sponsorship)\n"
        "- For salary questions: use the salary_expectation if provided, else say 'Negotiable'\n"
        "- For LinkedIn: use the linkedin_url if provided\n"
        "- For location/address: use the applicant's location\n"
        "- Skip questions you truly cannot answer (omit from output)\n\n"
        "Return a JSON object mapping question IDs to answer values. Example:\n"
        '{"12345": "Yes", "12346": "Austin, TX"}\n'
        "Return ONLY the JSON object, no markdown or explanation."
    ))

    human_msg = HumanMessage(content=(
        f"Job: {job_title} at {job_company}\n\n"
        f"Applicant profile:\n"
        f"- Name: {user_profile.get('name', 'N/A')}\n"
        f"- Email: {user_profile.get('email', 'N/A')}\n"
        f"- Phone: {user_profile.get('phone', 'N/A')}\n"
        f"- Location: {user_profile.get('location', 'N/A')}\n"
        f"- LinkedIn: {user_profile.get('linkedin_url', 'N/A')}\n"
        f"- GitHub: {user_profile.get('github_url', 'N/A')}\n"
        f"- Salary expectation: {user_profile.get('salary_expectation', 'Negotiable')}\n\n"
        f"Resume (excerpt):\n{resume_text[:3000]}\n\n"
        f"Cover letter:\n{cover_letter[:1500] if cover_letter else 'N/A'}\n\n"
        f"Questions to answer:\n{json.dumps(q_descriptions, indent=2)}"
    ))

    try:
        llm = build_llm(model=HAIKU_MODEL, max_tokens=2048, temperature=0.1)
        response = await invoke_with_retry(llm, [system_msg, human_msg], max_retries=2)
        text = response.content.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        answers = json.loads(text)
        return {f"question_{k}": str(v) for k, v in answers.items()}
    except Exception:
        logger.warning("LLM question answering failed — using fallback", exc_info=True)
        return _answer_questions_fallback(questions, user_profile)


def _answer_questions_fallback(
    questions: List[Dict],
    user_profile: Dict[str, str],
) -> Dict[str, str]:
    """Keyword-based fallback for answering Greenhouse questions."""
    answers: Dict[str, str] = {}
    for q in questions:
        q_id = q.get("id")
        label = (q.get("label") or "").lower()
        required = q.get("required", False)
        fields = q.get("fields", [])
        if not fields or not q_id:
            continue

        field = fields[0]
        field_type = field.get("type", "")
        values = field.get("values", [])

        if field_type in ("input_text", "textarea"):
            if "linkedin" in label:
                answers[f"question_{q_id}"] = user_profile.get("linkedin_url", "N/A")
            elif "github" in label:
                answers[f"question_{q_id}"] = user_profile.get("github_url", "N/A")
            elif "salary" in label or "compensation" in label:
                answers[f"question_{q_id}"] = user_profile.get("salary_expectation", "Negotiable")
            elif "address" in label or "location" in label or "city" in label:
                answers[f"question_{q_id}"] = user_profile.get("location", "N/A")
            elif required:
                answers[f"question_{q_id}"] = "N/A"

        elif field_type == "multi_value_single_select" and values:
            best = None
            for v in values:
                vlabel = (v.get("label") or "").lower()
                if "yes" in vlabel and any(kw in label for kw in ("authorization", "relocat", "open to", "in-person", "office", "eligible")):
                    best = v["value"]
                    break
                if "no" in vlabel and any(kw in label for kw in ("sponsor", "visa")):
                    best = v["value"]
                    break
                if "acknowledge" in vlabel or "agree" in vlabel or "confirm" in vlabel:
                    best = v["value"]
                    break
            if not best and values and required:
                best = values[0].get("value")
            if best:
                answers[f"question_{q_id}"] = str(best)

    return answers


# ---------------------------------------------------------------------------
# Greenhouse API submission
# ---------------------------------------------------------------------------

async def _apply_greenhouse(
    job: JobListing,
    user_profile: Dict[str, str],
    resume_text: str,
    cover_letter: str,
    resume_file_path: Optional[str],
    session_id: str,
) -> Optional[ApplicationResult]:
    """Submit application via Greenhouse Job Board API.

    Returns ApplicationResult on success/definitive failure.
    Returns None if blocked (reCAPTCHA) or API unavailable → caller falls back to Skyvern.
    """
    parsed = _parse_greenhouse_url(job.url)
    if not parsed:
        # Try external_apply_url
        if job.external_apply_url:
            parsed = _parse_greenhouse_url(job.external_apply_url)
    if not parsed:
        logger.info("Cannot parse Greenhouse URL from %s — skipping API path", job.url)
        return None

    board, job_id = parsed
    start = time.monotonic()

    async with aiohttp.ClientSession() as session:
        # 1. Fetch form schema (questions)
        try:
            async with session.get(
                f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}?questions=true",
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 404:
                    return ApplicationResult(
                        job_id=str(job.id),
                        status=ApplicationStatus.FAILED,
                        error_message="Job not found (404 from Greenhouse API)",
                        error_category=ApplicationErrorCategory.JOB_EXPIRED,
                        ats_type="greenhouse_api",
                        duration_seconds=int(time.monotonic() - start),
                    )
                if resp.status != 200:
                    logger.warning("Greenhouse API returned %d for job schema — falling back", resp.status)
                    return None
                job_detail = await resp.json()
        except Exception:
            logger.warning("Greenhouse API schema fetch failed — falling back", exc_info=True)
            return None

        questions = job_detail.get("questions", [])

        # 2. Answer custom questions via LLM
        question_answers = await _answer_greenhouse_questions(
            questions, user_profile, resume_text, cover_letter,
            job.title, job.company,
        )

        # 3. Build multipart form
        form = aiohttp.FormData()
        name_parts = (user_profile.get("name") or "").strip().split(" ", 1)
        form.add_field("first_name", name_parts[0] if name_parts else "")
        form.add_field("last_name", name_parts[1] if len(name_parts) > 1 else "")
        if user_profile.get("email"):
            form.add_field("email", user_profile["email"])
        if user_profile.get("phone"):
            form.add_field("phone", user_profile["phone"])

        # Resume file
        resume_data = _read_resume_bytes(resume_file_path)
        if resume_data:
            data, filename = resume_data
            form.add_field("resume", data, filename=filename, content_type="application/pdf")

        # Cover letter
        if cover_letter:
            form.add_field("cover_letter", cover_letter)

        # Custom question answers
        for field_name, value in question_answers.items():
            form.add_field(field_name, value)

        # 4. Submit
        logger.info(
            "Greenhouse API: submitting to %s/jobs/%s (%s at %s, %d questions answered)",
            board, job_id, job.title, job.company, len(question_answers),
        )
        try:
            async with session.post(
                f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}",
                data=form,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                status = resp.status
                body = await resp.text()
                elapsed = int(time.monotonic() - start)

                if status == 200:
                    logger.info(
                        "Greenhouse API: SUCCESS for %s at %s (took %ds)",
                        job.title, job.company, elapsed,
                    )
                    return ApplicationResult(
                        job_id=str(job.id),
                        status=ApplicationStatus.SUBMITTED,
                        ats_type="greenhouse_api",
                        duration_seconds=elapsed,
                        submitted_at=datetime.utcnow(),
                    )
                elif status == 428:
                    logger.info(
                        "Greenhouse API: reCAPTCHA required for %s — falling back to Skyvern",
                        board,
                    )
                    return None  # Fall back to Skyvern
                elif status == 422:
                    logger.warning(
                        "Greenhouse API: validation error for %s: %s",
                        job.title, body[:300],
                    )
                    return ApplicationResult(
                        job_id=str(job.id),
                        status=ApplicationStatus.FAILED,
                        error_message=f"Greenhouse API validation error: {body[:300]}",
                        error_category=ApplicationErrorCategory.FORM_FILL_ERROR,
                        ats_type="greenhouse_api",
                        duration_seconds=elapsed,
                    )
                else:
                    logger.warning(
                        "Greenhouse API: unexpected %d for %s — falling back",
                        status, job.title,
                    )
                    return None
        except Exception:
            logger.warning("Greenhouse API submit failed — falling back", exc_info=True)
            return None


# ---------------------------------------------------------------------------
# Lever API submission
# ---------------------------------------------------------------------------

async def _apply_lever(
    job: JobListing,
    user_profile: Dict[str, str],
    resume_text: str,
    cover_letter: str,
    resume_file_path: Optional[str],
    session_id: str,
) -> Optional[ApplicationResult]:
    """Submit application via Lever Postings API.

    Returns ApplicationResult on success/definitive failure.
    Returns None if API unavailable → caller falls back to Skyvern.
    """
    parsed = _parse_lever_url(job.url)
    if not parsed and job.external_apply_url:
        parsed = _parse_lever_url(job.external_apply_url)
    if not parsed:
        logger.info("Cannot parse Lever URL from %s — skipping API path", job.url)
        return None

    company, posting_id = parsed
    start = time.monotonic()

    async with aiohttp.ClientSession() as session:
        form = aiohttp.FormData()
        full_name = user_profile.get("name", "")
        form.add_field("name", full_name)
        if user_profile.get("email"):
            form.add_field("email", user_profile["email"])
        if user_profile.get("phone"):
            form.add_field("phone", user_profile["phone"])
        if user_profile.get("linkedin_url"):
            form.add_field("urls[LinkedIn]", user_profile["linkedin_url"])
        if user_profile.get("github_url"):
            form.add_field("urls[GitHub]", user_profile["github_url"])
        if user_profile.get("portfolio_url"):
            form.add_field("urls[Portfolio]", user_profile["portfolio_url"])
        if cover_letter:
            form.add_field("comments", cover_letter)

        resume_data = _read_resume_bytes(resume_file_path)
        if resume_data:
            data, filename = resume_data
            form.add_field("resume", data, filename=filename, content_type="application/pdf")

        logger.info(
            "Lever API: submitting to %s/%s (%s at %s)",
            company, posting_id, job.title, job.company,
        )
        try:
            async with session.post(
                f"https://api.lever.co/v0/postings/{company}/{posting_id}/apply",
                data=form,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                status = resp.status
                body = await resp.text()
                elapsed = int(time.monotonic() - start)

                if status == 200:
                    logger.info(
                        "Lever API: SUCCESS for %s at %s (took %ds)",
                        job.title, job.company, elapsed,
                    )
                    return ApplicationResult(
                        job_id=str(job.id),
                        status=ApplicationStatus.SUBMITTED,
                        ats_type="lever_api",
                        duration_seconds=elapsed,
                        submitted_at=datetime.utcnow(),
                    )
                elif status == 404:
                    return ApplicationResult(
                        job_id=str(job.id),
                        status=ApplicationStatus.FAILED,
                        error_message="Job not found (404 from Lever API)",
                        error_category=ApplicationErrorCategory.JOB_EXPIRED,
                        ats_type="lever_api",
                        duration_seconds=elapsed,
                    )
                else:
                    logger.warning(
                        "Lever API: %d for %s — falling back: %s",
                        status, job.title, body[:200],
                    )
                    return None
        except Exception:
            logger.warning("Lever API submit failed — falling back", exc_info=True)
            return None


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_ATS_HANDLERS = {
    ATSType.GREENHOUSE: _apply_greenhouse,
    ATSType.LEVER: _apply_lever,
}


async def apply_via_api(
    job: JobListing,
    user_profile: Dict[str, str],
    resume_text: str,
    cover_letter: str,
    resume_file_path: Optional[str],
    session_id: str,
) -> Optional[ApplicationResult]:
    """Try direct API submission for supported ATS platforms.

    Returns ApplicationResult on success or definitive failure.
    Returns None if the ATS has no API support or the API is blocked — caller
    should fall back to browser automation (Skyvern).
    """
    handler = _ATS_HANDLERS.get(job.ats_type)
    if handler is None:
        return None

    return await handler(
        job=job,
        user_profile=user_profile,
        resume_text=resume_text,
        cover_letter=cover_letter,
        resume_file_path=resume_file_path,
        session_id=session_id,
    )
