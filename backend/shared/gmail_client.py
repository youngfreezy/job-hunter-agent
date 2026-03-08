"""Gmail API client for automatic verification-code extraction.

Stores OAuth tokens per session in Redis, polls for recent
verification emails, and extracts numeric codes.  Falls back
gracefully -- never blocks the application flow.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
from typing import Optional

from backend.shared.redis_client import redis_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redis-backed token store  (key: gmail_token:{session_id})
# ---------------------------------------------------------------------------

_GMAIL_TOKEN_TTL = 7200  # 2 hours


async def store_gmail_token(
    session_id: str,
    access_token: str,
    refresh_token: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
) -> None:
    """Store a Gmail OAuth credential for *session_id* in Redis."""
    await redis_client.set_json(
        f"gmail_token:{session_id}",
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        expire_seconds=_GMAIL_TOKEN_TTL,
    )
    logger.info("Gmail token stored for session %s (refresh=%s)", session_id, bool(refresh_token))


async def clear_gmail_token(session_id: str) -> None:
    await redis_client.delete(f"gmail_token:{session_id}")


def _build_gmail_service(creds):
    """Build a Gmail API service from credentials."""
    from googleapiclient.discovery import build

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


async def _get_service(session_id: str):
    """Return a Gmail API service for *session_id*, or None."""
    data = await redis_client.get_json(f"gmail_token:{session_id}")
    if not data:
        return None
    try:
        from google.oauth2.credentials import Credentials

        creds = Credentials(
            token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=data.get("client_id"),
            client_secret=data.get("client_secret"),
        )
        return _build_gmail_service(creds)
    except Exception:
        logger.exception("Failed to build Gmail service for %s", session_id)
        return None


# ---------------------------------------------------------------------------
# Code extraction
# ---------------------------------------------------------------------------

# Patterns ordered from most specific to least specific
_CODE_PATTERNS = [
    # "Your verification code is 123456"
    re.compile(r"(?:verification|security|confirmation|one[- ]?time|otp)\s*(?:code|pin|number)?[\s:]+(\d{4,8})", re.I),
    # "Code: 123456" or "code 123456"
    re.compile(r"\bcode[\s:]+(\d{4,8})\b", re.I),
    # "Enter 123456 to verify"
    re.compile(r"\benter\s+(\d{4,8})\s+to\s+verify", re.I),
    # Standalone 4-8 digit number (last resort)
    re.compile(r"\b(\d{4,8})\b"),
]


def _extract_code(text: str) -> Optional[str]:
    """Extract a verification code from email body text."""
    for pattern in _CODE_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(1)
    return None


def _decode_body(payload: dict) -> str:
    """Decode the plain-text body from a Gmail message payload."""
    # Single-part message
    if "body" in payload and payload["body"].get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

    # Multi-part: find text/plain
    for part in payload.get("parts", []):
        mime = part.get("mimeType", "")
        if mime == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
        # Nested multipart
        if mime.startswith("multipart/"):
            nested = _decode_body(part)
            if nested:
                return nested

    # Fallback: try snippet
    return ""


# ---------------------------------------------------------------------------
# Main polling function
# ---------------------------------------------------------------------------

async def poll_for_verification_code(
    session_id: str,
    company: str = "",
    platform: str = "",
    max_wait: int = 90,
    poll_interval: int = 8,
) -> Optional[str]:
    """Poll Gmail for a recent verification-code email.

    Args:
        session_id: Current pipeline session.
        company: Company name to match in the email (e.g. "Greenhouse", "Netflix").
        platform: ATS platform name (e.g. "greenhouse", "lever").
        max_wait: Total seconds to keep polling.
        poll_interval: Seconds between each poll attempt.

    Returns the extracted code string, or None.
    """
    service = await _get_service(session_id)
    if not service:
        logger.warning("No Gmail token for session %s — skipping auto-extraction", session_id)
        return None

    # Build search query — look for very recent verification emails
    q_parts = ["is:unread", "newer_than:5m"]
    q_parts.append("(verification OR \"security code\" OR \"one-time\" OR OTP OR \"enter the code\" OR \"confirm your email\")")
    query = " ".join(q_parts)

    # Optional context keywords to prefer the right email
    context_keywords = set()
    if company:
        context_keywords.update(company.lower().split())
    if platform:
        context_keywords.add(platform.lower())

    attempts = max_wait // poll_interval
    for attempt in range(attempts):
        try:
            result = await asyncio.to_thread(
                lambda: service.users().messages().list(
                    userId="me", q=query, maxResults=5,
                ).execute()
            )
            messages = result.get("messages", [])

            # Score each message: prefer ones mentioning the company/platform
            best_code: Optional[str] = None
            best_score = -1

            for msg_stub in messages:
                msg = await asyncio.to_thread(
                    lambda mid=msg_stub["id"]: service.users().messages().get(
                        userId="me", id=mid, format="full",
                    ).execute()
                )

                snippet = (msg.get("snippet") or "").lower()
                payload = msg.get("payload", {})
                body_text = _decode_body(payload)

                code = _extract_code(body_text) or _extract_code(snippet)
                if not code:
                    continue

                # Score: +10 for each context keyword found in subject/snippet/body
                combined = (snippet + " " + body_text).lower()
                score = sum(10 for kw in context_keywords if kw in combined)
                # Boost emails that arrived very recently (snippet has them first anyway)
                score += 1  # baseline so any code beats no code

                if score > best_score:
                    best_score = score
                    best_code = code

            if best_code:
                logger.info(
                    "Gmail: extracted verification code (attempt %d/%d, score=%d)",
                    attempt + 1, attempts, best_score,
                )
                return best_code

        except Exception:
            logger.warning("Gmail poll attempt %d failed", attempt + 1, exc_info=True)

        if attempt < attempts - 1:
            await asyncio.sleep(poll_interval)

    logger.info("Gmail: no verification code found after %ds", max_wait)
    return None
