# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Twilio SMS webhook + phone verification routes."""

from __future__ import annotations

import logging
import random
import string

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from backend.shared.config import get_settings
from backend.shared.sms import send_verification_sms, verify_twilio_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sms", tags=["sms"])


# ---------------------------------------------------------------------------
# Inbound SMS webhook (Twilio → our server)
# ---------------------------------------------------------------------------

@router.post("/webhook")
async def twilio_webhook(request: Request):
    """Handle inbound SMS from Twilio. No JWT — verified by Twilio signature."""
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}

    # Verify Twilio signature
    signature = request.headers.get("X-Twilio-Signature", "")
    url = str(request.url)
    if not verify_twilio_signature(url, params, signature):
        logger.warning("Invalid Twilio signature on inbound SMS")
        raise HTTPException(status_code=403, detail="Invalid signature")

    from_number = params.get("From", "")
    body = params.get("Body", "").strip().upper()

    logger.info("Inbound SMS from %s: %s", from_number, body[:50])

    response_text = await _handle_command(from_number, body)

    # Return TwiML response
    return PlainTextResponse(
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response><Message>{response_text}</Message></Response>",
        media_type="application/xml",
    )


async def _handle_command(phone: str, command: str) -> str:
    """Parse and execute an SMS command. Returns the reply text."""
    # Look up user by phone
    user = await _get_user_by_phone(phone)

    if command == "HELP":
        return (
            "JobHunter commands:\n"
            "SEARCH <keywords> - Start a job search\n"
            "STATUS - Check latest session\n"
            "APPROVE - Approve pending autopilot jobs\n"
            "REJECT - Skip pending autopilot jobs\n"
            "PAUSE - Pause all autopilot schedules\n"
            "RESUME - Resume autopilot schedules\n"
            "HELP - This message"
        )

    if not user:
        return "Phone number not linked to a JobHunter account. Log in at jobhunteragent.com and add your number in Settings."

    user_id = user["id"]

    if command == "STATUS":
        return await _cmd_status(user_id)

    if command == "APPROVE":
        return await _cmd_approve(user_id)

    if command == "REJECT":
        return await _cmd_reject(user_id)

    if command == "PAUSE":
        return await _cmd_pause(user_id)

    if command == "RESUME":
        return await _cmd_resume(user_id)

    if command.startswith("SEARCH "):
        keywords = command[7:].strip()
        if not keywords:
            return "Usage: SEARCH <keywords>\nExample: SEARCH python engineer remote"
        return await _cmd_search(user_id, keywords)

    return "Unknown command. Reply HELP for options."


async def _cmd_status(user_id: str) -> str:
    from backend.shared.session_store import get_sessions_for_user
    sessions = get_sessions_for_user(user_id)
    if not sessions:
        return "No sessions found."
    latest = sessions[0]
    status = latest.get("status", "unknown")
    applied = latest.get("applications_submitted", 0)
    failed = latest.get("applications_failed", 0)
    return f"Latest session: {status}. Applied: {applied}, Failed: {failed}."


async def _cmd_approve(user_id: str) -> str:
    from backend.shared.autopilot_store import list_schedules
    from backend.gateway.routes.sessions import session_registry

    schedules = await list_schedules(user_id)
    for sched in schedules:
        sid = sched.get("last_session_id")
        if sid and session_registry.get(sid, {}).get("status") == "awaiting_review":
            from backend.gateway.routes.sessions import _resume_pipeline, _spawn_background
            from backend.gateway.main import _app_ref
            graph = _app_ref.state.graph if _app_ref else None
            if graph:
                _spawn_background(_resume_pipeline(
                    sid, graph,
                    resume_value={"approved": True, "approved_job_ids": "all"},
                ))
                return f"Approved! Session {sid[:8]} is now applying."
    return "No pending sessions to approve."


async def _cmd_reject(user_id: str) -> str:
    from backend.shared.autopilot_store import list_schedules
    from backend.gateway.routes.sessions import session_registry, _set_session_status

    schedules = await list_schedules(user_id)
    for sched in schedules:
        sid = sched.get("last_session_id")
        if sid and session_registry.get(sid, {}).get("status") == "awaiting_review":
            _set_session_status(sid, "failed")
            return f"Skipped session {sid[:8]}."
    return "No pending sessions to skip."


async def _cmd_pause(user_id: str) -> str:
    from backend.shared.autopilot_store import list_schedules, update_schedule
    schedules = await list_schedules(user_id)
    count = 0
    for sched in schedules:
        if sched.get("is_active"):
            await update_schedule(sched["id"], user_id, {"is_active": False})
            count += 1
    return f"Paused {count} schedule(s)." if count else "No active schedules to pause."


async def _cmd_resume(user_id: str) -> str:
    from backend.shared.autopilot_store import list_schedules, update_schedule
    from backend.shared.autopilot_runner import compute_next_run
    schedules = await list_schedules(user_id)
    count = 0
    for sched in schedules:
        if not sched.get("is_active"):
            next_run = compute_next_run(
                sched["cron_expression"],
                sched.get("timezone", "America/New_York"),
            )
            await update_schedule(sched["id"], user_id, {
                "is_active": True,
                "next_run_at": next_run,
            })
            count += 1
    return f"Resumed {count} schedule(s)." if count else "No paused schedules to resume."


async def _cmd_search(user_id: str, keywords_str: str) -> str:
    """Create a one-time session with the given keywords."""
    return (
        f"To start a search for \"{keywords_str}\", "
        f"visit jobhunteragent.com and create a new session. "
        f"SMS-triggered sessions coming soon!"
    )


async def _get_user_by_phone(phone: str):
    """Look up a user by phone number."""
    import asyncio
    import psycopg
    from backend.shared.config import get_settings

    def _fetch():
        try:
            with psycopg.connect(get_settings().DATABASE_URL) as conn:
                row = conn.execute(
                    "SELECT id, email FROM users WHERE phone_number = %s AND phone_verified = TRUE",
                    (phone,),
                ).fetchone()
                if row:
                    return {"id": str(row[0]), "email": row[1]}
        except Exception:
            logger.debug("phone lookup failed", exc_info=True)
        return None

    return await asyncio.to_thread(_fetch)


# ---------------------------------------------------------------------------
# Phone verification (JWT-authenticated)
# ---------------------------------------------------------------------------

class VerifyPhoneRequest(BaseModel):
    phone_number: str


class ConfirmPhoneRequest(BaseModel):
    code: str


@router.post("/verify")
async def send_verification(body: VerifyPhoneRequest, request: Request):
    """Send a 6-digit verification code to the user's phone."""
    from backend.gateway.deps import get_current_user
    user = get_current_user(request)
    user_id = user["id"]

    code = "".join(random.choices(string.digits, k=6))

    # Store code in Redis with 10-minute TTL
    from backend.shared.redis_client import redis_client
    await redis_client.client.setex(f"sms-verify:{user_id}", 600, code)

    # Also store the phone number being verified
    await redis_client.client.setex(f"sms-verify-phone:{user_id}", 600, body.phone_number)

    sent = await send_verification_sms(body.phone_number, code)
    if not sent:
        raise HTTPException(status_code=503, detail="Failed to send verification SMS")

    return {"sent": True}


@router.post("/confirm")
async def confirm_verification(body: ConfirmPhoneRequest, request: Request):
    """Confirm the verification code and link the phone number."""
    from backend.gateway.deps import get_current_user
    user = get_current_user(request)
    user_id = user["id"]

    from backend.shared.redis_client import redis_client
    stored_code = await redis_client.client.get(f"sms-verify:{user_id}")
    stored_phone = await redis_client.client.get(f"sms-verify-phone:{user_id}")

    if not stored_code or not stored_phone:
        raise HTTPException(status_code=400, detail="No pending verification. Send a code first.")

    stored_code_str = stored_code.decode() if isinstance(stored_code, bytes) else stored_code
    stored_phone_str = stored_phone.decode() if isinstance(stored_phone, bytes) else stored_phone

    if body.code != stored_code_str:
        raise HTTPException(status_code=400, detail="Invalid verification code")

    # Update user in DB
    import asyncio
    import psycopg

    def _update():
        with psycopg.connect(get_settings().DATABASE_URL) as conn:
            conn.execute(
                "UPDATE users SET phone_number = %s, phone_verified = TRUE WHERE id = %s",
                (stored_phone_str, user_id),
            )
            conn.commit()

    await asyncio.to_thread(_update)

    # Clean up Redis
    await redis_client.client.delete(f"sms-verify:{user_id}")
    await redis_client.client.delete(f"sms-verify-phone:{user_id}")

    return {"verified": True, "phone_number": stored_phone_str}
