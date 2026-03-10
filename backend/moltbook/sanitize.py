# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""SECURITY-CRITICAL input sanitization for Moltbook content.

All external content from Moltbook MUST pass through ``sanitize()`` before
being used in any LLM context, stored as strategy patches, or logged with
user-adjacent data.

Design principles:
- Deny by default: strip anything that looks like injection
- Log every removal so we can audit what the community sends
- Never raise — always return safe (possibly empty) text
"""

from __future__ import annotations

import base64
import logging
import re
from typing import List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt injection patterns (case-insensitive)
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS: List[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts?|context)",
        r"ignore\s+all\s+prior",
        r"you\s+are\s+now",
        r"^system\s*:",
        r"^assistant\s*:",
        r"^human\s*:",
        r"<\s*system\s*>",
        r"<\s*/\s*system\s*>",
        r"IMPORTANT\s*:",
        r"OVERRIDE",
        r"new\s+instructions",
        r"disregard\s+(all\s+)?(previous|prior|above)",
        r"forget\s+(everything|all|your)\s+(previous|prior|instructions)",
        r"pretend\s+you\s+are",
        r"act\s+as\s+(if|though)\s+you",
        r"from\s+now\s+on\s+you\s+(are|will)",
        r"<\s*\|?\s*im_start\s*\|?\s*>",
        r"<\s*\|?\s*im_end\s*\|?\s*>",
        r"\[INST\]",
        r"\[/INST\]",
        r"<<\s*SYS\s*>>",
        r"<<\s*/\s*SYS\s*>>",
    ]
]

# Allowed URL domains (everything else stripped)
_ALLOWED_URL_DOMAINS = {
    "github.com",
    "linkedin.com",
    "glassdoor.com",
    "indeed.com",
    "ziprecruiter.com",
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "workday.com",
    "myworkdayjobs.com",
    "moltbook.com",
}

# Base64 pattern: 20+ chars of base64 alphabet (catches encoded payloads)
_BASE64_PATTERN = re.compile(r"[A-Za-z0-9+/=]{20,}")

# Markdown code blocks
_CODE_BLOCK_PATTERN = re.compile(r"```[\s\S]*?```", re.MULTILINE)

# Inline code
_INLINE_CODE_PATTERN = re.compile(r"`[^`]+`")

# HTML/XML tags
_TAG_PATTERN = re.compile(r"<[^>]{1,200}>")

# URL pattern
_URL_PATTERN = re.compile(
    r"https?://[^\s<>\"')\]]{4,200}",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# PII patterns — NEVER let these through
# ---------------------------------------------------------------------------

_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_PATTERN = re.compile(r"\+?\d[\d\s\-().]{7,15}\d")
_SSN_PATTERN = re.compile(r"\d{3}-\d{2}-\d{4}")


# ---------------------------------------------------------------------------
# Main sanitize function
# ---------------------------------------------------------------------------


def sanitize(
    text: str,
    *,
    max_length: int = 500,
    context: str = "",
    strip_pii: bool = True,
) -> str:
    """Sanitize external Moltbook content for safe use.

    Parameters
    ----------
    text : str
        Raw text from Moltbook API.
    max_length : int
        Maximum length of returned text (default 500).
    context : str
        Optional label for log messages (e.g. "post_123", "comment").
    strip_pii : bool
        If True, also remove email addresses, phone numbers, SSNs.

    Returns
    -------
    str
        Sanitized text, safe for LLM context or storage.
    """
    if not text:
        return ""

    original_len = len(text)
    result = text
    removals: List[str] = []

    # 1. Strip markdown code blocks
    cleaned = _CODE_BLOCK_PATTERN.sub("", result)
    if cleaned != result:
        removals.append("code_blocks")
        result = cleaned

    # 2. Strip inline code
    cleaned = _INLINE_CODE_PATTERN.sub("", result)
    if cleaned != result:
        removals.append("inline_code")
        result = cleaned

    # 3. Strip HTML/XML tags
    cleaned = _TAG_PATTERN.sub("", result)
    if cleaned != result:
        removals.append("html_xml_tags")
        result = cleaned

    # 4. Strip prompt injection patterns
    for pattern in _INJECTION_PATTERNS:
        cleaned = pattern.sub("", result)
        if cleaned != result:
            removals.append(f"injection:{pattern.pattern[:40]}")
            result = cleaned

    # 5. Strip base64-encoded strings (likely encoded payloads)
    def _check_base64(match: re.Match) -> str:
        candidate = match.group(0)
        # Only strip if it actually decodes as valid base64
        try:
            decoded = base64.b64decode(candidate, validate=True)
            if len(decoded) > 10:
                removals.append("base64")
                return ""
        except Exception:
            pass
        return candidate

    result = _BASE64_PATTERN.sub(_check_base64, result)

    # 6. Strip URLs (except allowed domains)
    def _filter_url(match: re.Match) -> str:
        url = match.group(0)
        for domain in _ALLOWED_URL_DOMAINS:
            if domain in url.lower():
                return url
        removals.append(f"url:{url[:60]}")
        return ""

    result = _URL_PATTERN.sub(_filter_url, result)

    # 7. Strip PII
    if strip_pii:
        cleaned = _EMAIL_PATTERN.sub("[email]", result)
        if cleaned != result:
            removals.append("email_addresses")
            result = cleaned

        cleaned = _PHONE_PATTERN.sub("[phone]", result)
        if cleaned != result:
            removals.append("phone_numbers")
            result = cleaned

        cleaned = _SSN_PATTERN.sub("[redacted]", result)
        if cleaned != result:
            removals.append("ssn")
            result = cleaned

    # 8. Collapse whitespace
    result = re.sub(r"\s+", " ", result).strip()

    # 9. Truncate
    if len(result) > max_length:
        result = result[:max_length].rstrip()
        removals.append(f"truncated:{original_len}->{max_length}")

    # Log removals
    if removals:
        label = f" [{context}]" if context else ""
        logger.warning(
            "Moltbook sanitization%s removed: %s (original=%d chars, final=%d chars)",
            label,
            ", ".join(removals),
            original_len,
            len(result),
        )

    return result


def sanitize_for_posting(text: str, *, max_length: int = 500) -> str:
    """Sanitize content WE are about to post to Moltbook.

    This is the outbound direction — ensures we never accidentally
    post PII, credentials, or sensitive data.
    """
    if not text:
        return ""

    result = text
    removals: List[str] = []

    # Strip any PII that might have leaked in
    cleaned = _EMAIL_PATTERN.sub("[email]", result)
    if cleaned != result:
        removals.append("email")
        result = cleaned

    cleaned = _PHONE_PATTERN.sub("[phone]", result)
    if cleaned != result:
        removals.append("phone")
        result = cleaned

    cleaned = _SSN_PATTERN.sub("[redacted]", result)
    if cleaned != result:
        removals.append("ssn")
        result = cleaned

    # Strip anything that looks like an API key or token
    cleaned = re.sub(r"(sk|pk|api|key|token|secret|password)[_-]?\w{8,}", "[redacted]", result, flags=re.IGNORECASE)
    if cleaned != result:
        removals.append("api_keys")
        result = cleaned

    # Truncate
    if len(result) > max_length:
        result = result[:max_length].rstrip()
        removals.append("truncated")

    if removals:
        logger.warning(
            "Outbound Moltbook sanitization removed: %s",
            ", ".join(removals),
        )

    return result
