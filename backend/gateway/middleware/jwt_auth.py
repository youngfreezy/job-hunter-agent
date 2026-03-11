# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""JWT authentication middleware — decrypts NextAuth v4 JWE tokens.

NextAuth v4 (JWT strategy) encrypts session tokens as JWE using:
- Key derivation: HKDF(SHA-256, secret, salt="", info="NextAuth.js Generated Encryption Key")
- Encryption: A256GCM with "dir" key management

This middleware extracts the Authorization: Bearer <token> header, decrypts
the JWE, and sets request.state.user_email for downstream route handlers.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

from backend.shared.config import get_settings

logger = logging.getLogger(__name__)

_EXEMPT_PATHS = {
    "/api/health",
    "/api/health/ready",
    "/api/stripe/webhook",
}
_EXEMPT_PREFIXES = (
    "/docs",
    "/openapi",
    "/redoc",
    "/api/autopilot/approve/",
    "/api/sms/webhook",
    "/api/free-trial",
)


def _base64url_decode(s: str) -> bytes:
    """Decode base64url without padding."""
    s += "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)


def _derive_encryption_key(secret: str) -> bytes:
    """Derive the 256-bit encryption key NextAuth uses for JWE."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"",
        info=b"NextAuth.js Generated Encryption Key",
    )
    return hkdf.derive(secret.encode("utf-8"))


def decrypt_nextauth_jwt(token: str, secret: str) -> dict:
    """Decrypt a NextAuth v4 JWE compact-serialization token.

    Returns the decrypted payload as a dict.
    Raises ValueError on any decryption failure.
    """
    parts = token.split(".")
    if len(parts) != 5:
        raise ValueError(f"Invalid JWE: expected 5 parts, got {len(parts)}")

    header_b64, _enc_key_b64, iv_b64, ciphertext_b64, tag_b64 = parts

    iv = _base64url_decode(iv_b64)
    ciphertext = _base64url_decode(ciphertext_b64)
    tag = _base64url_decode(tag_b64)

    key = _derive_encryption_key(secret)
    aesgcm = AESGCM(key)

    # AAD (Additional Authenticated Data) is the ASCII-encoded protected header
    aad = header_b64.encode("ascii")

    # AES-GCM expects nonce, ciphertext||tag, aad
    plaintext = aesgcm.decrypt(iv, ciphertext + tag, aad)
    return json.loads(plaintext)


_TRIAL_TOKEN_TTL = 24 * 60 * 60  # 24 hours


def create_trial_token(user_id: str) -> str:
    """Create an HMAC-signed trial token for anonymous free-trial users."""
    secret = get_settings().NEXTAUTH_SECRET or ""
    payload = json.dumps({"uid": user_id, "iat": int(time.time())})
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    encoded = base64.urlsafe_b64encode(payload.encode()).decode()
    return f"trial_{encoded}.{sig}"


def _verify_trial_token(token: str) -> Optional[str]:
    """Verify a trial token and return user_id, or None if invalid/expired."""
    if not token.startswith("trial_"):
        return None
    try:
        body = token[6:]  # strip "trial_"
        encoded, sig = body.rsplit(".", 1)
        payload_bytes = base64.urlsafe_b64decode(encoded)
        secret = get_settings().NEXTAUTH_SECRET or ""
        expected_sig = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload = json.loads(payload_bytes)
        if time.time() - payload.get("iat", 0) > _TRIAL_TOKEN_TTL:
            return None
        return payload.get("uid")
    except Exception:
        return None


def _extract_email(request: Request) -> Optional[str]:
    """Try to extract user email from JWT in Authorization header or query param.

    EventSource (SSE) cannot send custom headers, so we also accept
    ``?token=<jwt>`` for SSE stream endpoints.
    """
    token: Optional[str] = None

    # 1. Prefer Authorization header
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]

    # 2. Fall back to ?token= query param (for EventSource / SSE)
    if not token:
        token = request.query_params.get("token")

    if not token:
        return None

    # Check for API key auth (jh_live_*)
    if token.startswith("jh_live_"):
        try:
            from backend.shared.api_key_store import validate_api_key
            result = validate_api_key(token)
            if result:
                return result["email"]
        except Exception as exc:
            logger.debug("API key validation failed: %s", exc)
        return None

    secret = get_settings().NEXTAUTH_SECRET
    if not secret:
        logger.error("NEXTAUTH_SECRET not configured — cannot validate JWTs")
        return None

    try:
        payload = decrypt_nextauth_jwt(token, secret)
    except Exception as exc:
        logger.debug("JWT decryption failed: %s", exc)
        return None

    email = payload.get("email")
    if not email or not isinstance(email, str):
        logger.debug("JWT payload missing email field: %s", list(payload.keys()))
        return None

    return email


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Validate NextAuth JWT and attach user email to request state."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip exempt paths
        if path in _EXEMPT_PATHS or path.startswith(_EXEMPT_PREFIXES):
            request.state.user_email = None
            response = await call_next(request)
            return response

        # Try JWT-based auth
        email = _extract_email(request)
        request.state.user_email = email  # None if JWT missing/invalid

        # Try trial token if no JWT email found
        request.state.trial_user_id = None
        if not email:
            token = request.headers.get("authorization", "")[7:] if request.headers.get("authorization", "").startswith("Bearer ") else ""
            if not token:
                token = request.query_params.get("token", "")
            if token and token.startswith("trial_"):
                trial_uid = _verify_trial_token(token)
                if trial_uid:
                    request.state.trial_user_id = trial_uid

        response = await call_next(request)
        return response


def attach_jwt_auth(app: FastAPI) -> None:
    """Add JWT auth middleware to the FastAPI app."""
    app.add_middleware(JWTAuthMiddleware)
    logger.info("JWT auth middleware attached")
