# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Free trial endpoints — allow anonymous users to run one session without signup."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import bcrypt
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from backend.shared.billing_store import (
    convert_anonymous_user,
    create_anonymous_user,
)
from backend.shared.config import get_settings
from backend.shared.models.schemas import StartSessionRequest
from backend.shared.redis_client import redis_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/free-trial", tags=["free-trial"])

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _extract_email_from_text(text: str) -> Optional[str]:
    """Extract the first email address found in resume text."""
    match = _EMAIL_RE.search(text)
    return match.group(0).lower() if match else None


def _extract_name_from_text(text: str) -> Optional[str]:
    """Heuristic: the first non-empty line of a resume is usually the name."""
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or "@" in line or line.startswith("http"):
            continue
        # Skip lines that look like headers/titles
        if len(line) > 60 or line.isupper():
            continue
        return line
    return None


async def _check_rate_limits(email: str, client_ip: str) -> None:
    """Enforce rate limits: 2 per IP/day, 50 global/day."""
    try:
        # IP rate limit
        ip_key = f"free_trial:ip:{client_ip}"
        ip_count = await redis_client.incr(ip_key)
        if ip_count == 1:
            await redis_client.expire(ip_key, 86400)
        if ip_count > 2:
            raise HTTPException(
                status_code=429,
                detail="Too many free trial attempts from this network. Please try again tomorrow or sign up for an account.",
            )

        # Global rate limit
        global_key = "free_trial:global:daily"
        global_count = await redis_client.incr(global_key)
        if global_count == 1:
            await redis_client.expire(global_key, 86400)
        if global_count > 50:
            raise HTTPException(
                status_code=429,
                detail="Free trials are temporarily at capacity. Please sign up for an account or try again later.",
            )
    except HTTPException:
        raise
    except Exception:
        # Redis unavailable — allow through (graceful degradation)
        logger.debug("Redis unavailable for free trial rate limiting", exc_info=True)


# ---------------------------------------------------------------------------
# POST /api/free-trial/parse-resume
# ---------------------------------------------------------------------------


@router.post("/parse-resume")
async def free_trial_parse_resume(request: Request, file: UploadFile = File(...)):
    """Parse a resume without requiring authentication. Same logic as /api/sessions/parse-resume."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    suffix = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""

    MAX_RESUME_BYTES = 10 * 1024 * 1024
    raw = await file.read(MAX_RESUME_BYTES + 1)
    if len(raw) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=413, detail="Resume file exceeds 10 MB limit")

    # Validate file signatures
    if suffix == "pdf" and not raw[:4].startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="File does not appear to be a valid PDF")
    if suffix == "docx" and not raw[:4].startswith(b"PK\x03\x04"):
        raise HTTPException(status_code=400, detail="File does not appear to be a valid DOCX")

    if suffix == "txt":
        text = raw.decode("utf-8", errors="replace")
    elif suffix == "pdf":
        import io
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise HTTPException(status_code=500, detail="PDF parsing dependency missing") from exc
        reader = PdfReader(io.BytesIO(raw))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if not text.strip():
            try:
                import fitz
                import pytesseract
                from PIL import Image
                doc = fitz.open(stream=raw, filetype="pdf")
                ocr_parts = []
                for page in doc:
                    pix = page.get_pixmap(dpi=300)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    ocr_parts.append(pytesseract.image_to_string(img))
                text = "\n".join(ocr_parts)
            except Exception as ocr_err:
                logger.warning("OCR fallback failed: %s", ocr_err)
    elif suffix == "docx":
        import io
        try:
            from docx import Document
        except ImportError as exc:
            raise HTTPException(status_code=500, detail="DOCX parsing dependency missing") from exc
        doc = Document(io.BytesIO(raw))
        text = "\n".join(p.text for p in doc.paragraphs)
    elif suffix == "doc":
        raise HTTPException(status_code=400, detail="Legacy .doc not supported. Upload .docx, .pdf, or .txt.")
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: .{suffix}")

    text = text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Could not extract any text from the file")

    # Persist resume to Postgres (same pattern as sessions.parse_resume)
    import os
    import tempfile
    from backend.shared.resume_crypto import encrypt_and_save

    resume_dir = os.path.join(tempfile.gettempdir(), "jobhunter_resumes")
    os.makedirs(resume_dir, exist_ok=True)
    file_uuid = uuid.uuid4().hex
    plaintext_path = os.path.join(resume_dir, f"{file_uuid}.{suffix}")
    enc_path = encrypt_and_save(raw, plaintext_path)

    try:
        from backend.shared.resume_store import save_resume as _save_resume_db
        with open(enc_path, "rb") as ef:
            _save_resume_db(file_uuid, ef.read(), f".{suffix}")
    except Exception:
        logger.warning("Failed to persist resume in free-trial parse-resume", exc_info=True)

    return {"text": text, "filename": file.filename, "file_path": enc_path, "resume_uuid": file_uuid}


# ---------------------------------------------------------------------------
# POST /api/free-trial/start
# ---------------------------------------------------------------------------


@router.post("/start")
async def free_trial_start(body: StartSessionRequest, request: Request):
    """Start a free trial session without authentication.

    Extracts email from resume text, creates anonymous user, runs pipeline.
    Returns session_id + trial_token for SSE auth.
    """
    if not body.resume_text:
        raise HTTPException(status_code=400, detail="Resume text is required for free trial")

    email = _extract_email_from_text(body.resume_text)
    if not email:
        raise HTTPException(
            status_code=400,
            detail="Could not find an email address in your resume. Please ensure your resume includes your email.",
        )

    name = _extract_name_from_text(body.resume_text)

    # Rate limit by IP
    client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown").split(",")[0].strip()
    await _check_rate_limits(email, client_ip)

    # Create anonymous user (or get existing anonymous user with remaining credits)
    anon_user = create_anonymous_user(email, name)
    if anon_user is None:
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists or the free trial has been used. Please sign in to continue.",
        )

    user_id = anon_user["id"]

    # Create trial token for subsequent requests (SSE, etc.)
    from backend.gateway.middleware.jwt_auth import create_trial_token
    trial_token = create_trial_token(user_id)

    # Run the session — reuse the same pipeline logic as authenticated sessions
    from backend.gateway.routes.sessions import (
        _run_pipeline,
        _spawn_background,
        event_logs,
        session_registry,
        sse_subscribers,
    )
    from backend.shared.session_store import upsert_session
    from backend.shared.task_queue import enqueue_session, mark_active

    session_id = str(uuid.uuid4())
    graph = request.app.state.graph

    # Enforce concurrency limits
    try:
        enqueued = await enqueue_session(session_id, user_id)
        if not enqueued:
            raise HTTPException(status_code=429, detail="Please wait for your current session to finish.")
        await mark_active(session_id)
    except HTTPException:
        raise
    except Exception:
        logger.debug("Task queue unavailable — skipping concurrency check", exc_info=True)

    event_logs[session_id] = []
    sse_subscribers[session_id] = []

    session_meta = {
        "session_id": session_id,
        "user_id": user_id,
        "status": "intake",
        "keywords": body.keywords,
        "locations": body.locations,
        "remote_only": body.remote_only,
        "salary_min": body.salary_min,
        "resume_text_snippet": (body.resume_text or "")[:200],
        "linkedin_url": body.linkedin_url,
        "applications_submitted": 0,
        "applications_failed": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_free_trial": True,
    }
    session_registry[session_id] = session_meta
    upsert_session(session_id, session_meta)

    # Re-key resume from parse-time UUID to session_id
    file_uuid = body.resume_uuid
    if not file_uuid and body.resume_file_path:
        import os
        basename = os.path.basename(body.resume_file_path)
        file_uuid = basename.split(".")[0]

    if file_uuid:
        try:
            from backend.shared.resume_store import save_resume as _save_resume_db, get_resume as _get_resume_db
            row = _get_resume_db(file_uuid)
            if row:
                enc_data, ext = row
                _save_resume_db(session_id, enc_data, ext)
        except Exception:
            logger.warning("Failed to re-key resume in free-trial start", exc_info=True)

    _spawn_background(_run_pipeline(session_id, body, graph, user_id=user_id))

    return {
        "session_id": session_id,
        "trial_token": trial_token,
        "email": email,
        "name": name,
    }


# ---------------------------------------------------------------------------
# POST /api/free-trial/convert
# ---------------------------------------------------------------------------


class ConvertRequest(BaseModel):
    trial_token: str
    password: str
    name: Optional[str] = None


@router.post("/convert")
async def free_trial_convert(body: ConvertRequest, request: Request):
    """Convert an anonymous free-trial user to a full account."""
    from backend.gateway.middleware.jwt_auth import _verify_trial_token

    user_id = _verify_trial_token(body.trial_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired trial token")

    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()

    result = convert_anonymous_user(
        user_id=user_id,
        password_hash=password_hash,
        name=body.name,
        auth_provider="email",
    )
    if not result:
        raise HTTPException(status_code=404, detail="User not found or already converted")

    return {
        "status": "converted",
        "email": result["email"],
        "name": result.get("name"),
    }
