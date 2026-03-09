# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""SMS helpers using the Twilio REST API.

Mirrors the email_notifications.py pattern: async send, graceful degradation.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from backend.shared.config import get_settings

logger = logging.getLogger(__name__)

_TWILIO_API = "https://api.twilio.com/2010-04-01"


# ---------------------------------------------------------------------------
# Low-level sender
# ---------------------------------------------------------------------------

async def send_sms(to: str, body: str) -> bool:
    """Send an SMS via the Twilio REST API.

    Returns True on success, False on failure (missing config, API error).
    """
    settings = get_settings()
    sid = settings.TWILIO_ACCOUNT_SID
    token = settings.TWILIO_AUTH_TOKEN
    from_number = settings.TWILIO_PHONE_NUMBER

    if not sid or not token or not from_number:
        logger.warning("Twilio not configured — skipping SMS to %s", to)
        return False

    url = f"{_TWILIO_API}/Accounts/{sid}/Messages.json"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                auth=(sid, token),
                data={
                    "To": to,
                    "From": from_number,
                    "Body": body,
                },
            )
        if resp.status_code >= 400:
            logger.error("Twilio API error %s: %s", resp.status_code, resp.text)
            return False
        logger.info("SMS sent to %s", to)
        return True
    except httpx.HTTPError as exc:
        logger.error("Failed to send SMS to %s: %s", to, exc)
        return False


# ---------------------------------------------------------------------------
# Twilio webhook signature verification
# ---------------------------------------------------------------------------

def verify_twilio_signature(url: str, params: dict, signature: str) -> bool:
    """Verify an inbound Twilio webhook request signature."""
    settings = get_settings()
    token = settings.TWILIO_AUTH_TOKEN
    if not token:
        return False

    import hashlib
    import hmac
    import base64

    # Twilio signature = Base64(HMAC-SHA1(AuthToken, URL + sorted POST params))
    data = url
    for key in sorted(params.keys()):
        data += key + params[key]

    expected = base64.b64encode(
        hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()
    ).decode()

    return hmac.compare_digest(signature, expected)


# ---------------------------------------------------------------------------
# SMS notification helpers
# ---------------------------------------------------------------------------

def _verify_user_phone(user_id: str, phone: str) -> bool:
    """Check that the phone number belongs to the user."""
    from backend.shared.db import get_connection
    try:
        with get_connection() as conn:
            cur = conn.execute(
                "SELECT phone FROM users WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            if not row or not row[0]:
                return False
            # Normalize: strip spaces/dashes for comparison
            stored = row[0].replace(" ", "").replace("-", "")
            given = phone.replace(" ", "").replace("-", "")
            return stored == given
    except Exception:
        logger.warning("Failed to verify phone for user %s", user_id, exc_info=True)
        return False


async def send_session_complete_sms(
    to_phone: str,
    session_id: str,
    total_applied: int,
    total_failed: int,
) -> bool:
    """Send a session-complete summary via SMS."""
    body = (
        f"JobHunter: Session complete! "
        f"{total_applied} applied, {total_failed} failed. "
        f"View results: https://jobhunteragent.com/session/{session_id}"
    )
    return await send_sms(to_phone, body)


async def send_autopilot_approval_sms(
    to_phone: str,
    schedule_name: str,
    jobs_found: int,
    session_id: str,
    user_id: Optional[str] = None,
) -> bool:
    """Send an autopilot approval request via SMS.

    When *user_id* is provided, validates that *to_phone* matches the user's
    stored phone number to prevent sending SMS to arbitrary numbers.
    """
    if user_id:
        verified = _verify_user_phone(user_id, to_phone)
        if not verified:
            logger.warning("SMS blocked: phone %s not verified for user %s", to_phone, user_id)
            return False
    body = (
        f"JobHunter Autopilot: \"{schedule_name}\" found {jobs_found} jobs. "
        f"Reply APPROVE to apply or REJECT to skip. "
        f"View: https://jobhunteragent.com/session/{session_id}"
    )
    return await send_sms(to_phone, body)


async def send_verification_sms(to_phone: str, code: str) -> bool:
    """Send a phone verification code."""
    body = f"Your JobHunter verification code is: {code}. Expires in 10 minutes."
    return await send_sms(to_phone, body)
