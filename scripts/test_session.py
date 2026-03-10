#!/usr/bin/env python3
# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""CLI test script — creates a session, auto-approves coaching, monitors progress.

Usage:
    python scripts/test_session.py                          # production
    python scripts/test_session.py --env staging            # staging
    python scripts/test_session.py --env local              # local dev
    python scripts/test_session.py --resume /path/to/resume.pdf
    python scripts/test_session.py --keywords "React" "Node.js" --remote
    python scripts/test_session.py --skip-coaching          # auto-approve immediately
    python scripts/test_session.py --max-jobs 5             # limit jobs

Requires: pip install requests cryptography pypdf
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

# ---------------------------------------------------------------------------
# Environment configs
# ---------------------------------------------------------------------------

ENVS = {
    "production": {
        "api": "https://backend-production-cf19.up.railway.app",
        "secret": "QQD7SGSZkKqJM9b4Lr1weNwI69eZ5VkdnYDg",
    },
    "staging": {
        "api": "https://backend-staging-a1c9.up.railway.app",
        "secret": "QQD7SGSZkKqJM9b4Lr1weNwI69eZ5VkdnYDg",
    },
    "local": {
        "api": "http://localhost:8000",
        "secret": os.environ.get("NEXTAUTH_SECRET", "dev-secret-change-me"),
    },
}

DEFAULT_RESUME = os.path.expanduser(
    "~/Desktop/Jane_Doe_Resume_Generated.pdf"
)
DEFAULT_EMAIL = "jane.doe@example.com"

# ---------------------------------------------------------------------------
# JWE token minting (NextAuth v4 compatible)
# ---------------------------------------------------------------------------


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def mint_jwe(email: str, secret: str) -> str:
    """Create a NextAuth-compatible JWE token."""
    # Derive key same as NextAuth
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"",
        info=b"NextAuth.js Generated Encryption Key",
    )
    key = hkdf.derive(secret.encode("utf-8"))

    # Header: {"alg":"dir","enc":"A256GCM"}
    header = _base64url_encode(json.dumps({"alg": "dir", "enc": "A256GCM"}).encode())

    # Payload
    payload = json.dumps({
        "email": email,
        "name": email.split("@")[0],
        "iat": int(time.time()),
        "exp": int(time.time()) + 86400,
    }).encode()

    # Encrypt
    iv = os.urandom(12)
    aesgcm = AESGCM(key)
    aad = header.encode("ascii")
    ct_and_tag = aesgcm.encrypt(iv, payload, aad)
    ciphertext = ct_and_tag[:-16]
    tag = ct_and_tag[-16:]

    # JWE compact: header.enc_key.iv.ciphertext.tag (enc_key empty for "dir")
    return ".".join([
        header,
        "",  # empty encrypted key for direct key agreement
        _base64url_encode(iv),
        _base64url_encode(ciphertext),
        _base64url_encode(tag),
    ])


# ---------------------------------------------------------------------------
# Resume parsing
# ---------------------------------------------------------------------------


def extract_resume_text(path: str) -> str:
    """Extract text from a PDF resume."""
    from pypdf import PdfReader
    reader = PdfReader(path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if not text.strip():
        raise RuntimeError(f"Could not extract text from {path}")
    return text.strip()


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def api(method: str, url: str, token: str, **kwargs) -> requests.Response:
    """Make an authenticated API request."""
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    resp = requests.request(method, url, headers=headers, **kwargs)
    return resp


def upload_resume(base_url: str, token: str, resume_path: str) -> dict:
    """Upload resume and get back text + encrypted file path."""
    with open(resume_path, "rb") as f:
        resp = api(
            "POST",
            f"{base_url}/api/sessions/parse-resume",
            token,
            files={"file": (os.path.basename(resume_path), f, "application/pdf")},
        )
    resp.raise_for_status()
    return resp.json()


def create_session(
    base_url: str,
    token: str,
    resume_text: str,
    resume_file_path: str,
    keywords: list[str],
    remote_only: bool,
    max_jobs: int,
    job_boards: list[str],
) -> str:
    """Create a new session and return session_id."""
    body = {
        "keywords": keywords,
        "locations": ["Remote"] if remote_only else [],
        "remote_only": remote_only,
        "salary_min": None,
        "search_radius": 100,
        "country": "US",
        "resume_text": resume_text,
        "resume_file_path": resume_file_path,
        "linkedin_url": None,
        "preferences": {},
        "config": {
            "max_jobs": max_jobs,
            "tailoring_quality": "standard",
            "application_mode": "auto_apply",
            "generate_cover_letters": True,
            "job_boards": job_boards,
            "ai_temperature": 0.0,
            "scoring_strictness": 0.5,
        },
    }
    resp = api("POST", f"{base_url}/api/sessions", token, json=body)
    resp.raise_for_status()
    data = resp.json()
    return data["session_id"]


def approve_coaching(base_url: str, token: str, session_id: str) -> None:
    """Auto-approve the coach review step."""
    resp = api(
        "POST",
        f"{base_url}/api/sessions/{session_id}/coach-review",
        token,
        json={"approved": True, "edited_resume": None, "feedback": "Auto-approved by CLI test"},
    )
    if resp.status_code == 200:
        print("  ✓ Coach review approved")
    else:
        print(f"  ⚠ Coach review response: {resp.status_code} {resp.text[:200]}")


def approve_shortlist(base_url: str, token: str, session_id: str, job_ids: list[str]) -> None:
    """Auto-approve all jobs in the shortlist."""
    resp = api(
        "POST",
        f"{base_url}/api/sessions/{session_id}/review",
        token,
        json={"approved_job_ids": job_ids, "feedback": "Auto-approved by CLI test"},
    )
    if resp.status_code == 200:
        print(f"  ✓ Shortlist approved ({len(job_ids)} jobs)")
    else:
        print(f"  ⚠ Shortlist review response: {resp.status_code} {resp.text[:200]}")


# ---------------------------------------------------------------------------
# SSE monitor
# ---------------------------------------------------------------------------


def monitor_session(
    base_url: str,
    token: str,
    session_id: str,
    auto_approve_coaching: bool = True,
    auto_approve_shortlist: bool = True,
) -> None:
    """Stream SSE events and print progress. Auto-approves HITL gates."""
    stream_url = f"{base_url}/api/sessions/{session_id}/stream?token={token}"
    print(f"\n📡 Streaming events from session {session_id}...")
    print(f"   URL: {base_url.replace('backend-production-cf19.up.railway.app', 'jobhunteragent.com')}/session/{session_id}")
    print()

    coaching_approved = False
    shortlist_approved = False

    try:
        resp = requests.get(stream_url, stream=True, timeout=600)
        resp.raise_for_status()

        event_type = None
        data_lines = []

        for line in resp.iter_lines(decode_unicode=True):
            if line is None:
                continue

            if line.startswith("event:"):
                event_type = line[6:].strip()
                data_lines = []
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
            elif line == "" and event_type:
                # End of event
                raw_data = "\n".join(data_lines)
                try:
                    data = json.loads(raw_data)
                except (json.JSONDecodeError, ValueError):
                    data = {"raw": raw_data}

                ts = datetime.now().strftime("%H:%M:%S")
                _print_event(ts, event_type, data)

                # Auto-approve coaching
                if (
                    auto_approve_coaching
                    and not coaching_approved
                    and event_type in ("coach_review", "status")
                    and data.get("status") in ("awaiting_coach_review", "paused")
                ):
                    print(f"\n  🤖 Auto-approving coaching...")
                    time.sleep(2)
                    approve_coaching(base_url, token, session_id)
                    coaching_approved = True

                # Auto-approve shortlist
                if (
                    auto_approve_shortlist
                    and not shortlist_approved
                    and event_type in ("hitl", "status")
                    and data.get("status") == "awaiting_review"
                ):
                    shortlist = data.get("shortlist", [])
                    job_ids = [j.get("job", {}).get("id", j.get("id", "")) for j in shortlist]
                    job_ids = [jid for jid in job_ids if jid]
                    if job_ids:
                        print(f"\n  🤖 Auto-approving shortlist ({len(job_ids)} jobs)...")
                        time.sleep(2)
                        approve_shortlist(base_url, token, session_id, job_ids)
                        shortlist_approved = True

                # Terminal
                if event_type == "done" or data.get("status") == "completed":
                    print("\n✅ Session complete!")
                    _print_summary(data)
                    return

                if data.get("status") == "error":
                    print(f"\n❌ Session error: {data.get('message', 'unknown')}")
                    return

                event_type = None
                data_lines = []

    except KeyboardInterrupt:
        print("\n\n⏹  Stopped monitoring (session continues in background)")
    except Exception as e:
        print(f"\n❌ Stream error: {e}")


def _print_event(ts: str, event_type: str, data: dict):
    """Pretty-print an SSE event."""
    status = data.get("status", "")
    message = data.get("message", "")
    step = data.get("step", "")
    board = data.get("board", "")
    count = data.get("count")
    progress = data.get("progress")

    # Skip pings
    if event_type == "ping":
        return

    # Discovery progress
    if event_type == "discovery_progress" or step:
        icon = "🔍" if not data.get("error") else "⚠️"
        suffix = f" ({count} jobs)" if count else ""
        pct = f" [{progress}%]" if progress else ""
        print(f"  {ts} {icon} {step or message}{suffix}{pct}")
        return

    # Status updates
    icons = {
        "intake": "📋",
        "coaching": "📝",
        "awaiting_coach_review": "⏸️",
        "discovering": "🔍",
        "scoring": "📊",
        "tailoring": "✂️",
        "applying": "📨",
        "awaiting_review": "⏸️",
        "completed": "✅",
        "error": "❌",
        "paused": "⏸️",
    }
    icon = icons.get(status, "📡")

    # Job counts
    jobs_found = data.get("jobs_found")
    scored = data.get("scored_count")
    shortlist = data.get("shortlist", [])

    extra = ""
    if jobs_found:
        extra = f" — {jobs_found} jobs found"
    elif scored:
        extra = f" — {scored} jobs scored"
    elif shortlist:
        extra = f" — {len(shortlist)} jobs shortlisted"

    display = message or status or event_type
    print(f"  {ts} {icon} [{event_type}] {display}{extra}")


def _print_summary(data: dict):
    """Print session summary."""
    summary = data.get("session_summary", data)
    if not summary:
        return
    print()
    print("  ╔══════════════════════════════════╗")
    print("  ║        SESSION SUMMARY           ║")
    print("  ╠══════════════════════════════════╣")
    for key in ("total_discovered", "total_scored", "total_applied", "total_failed", "avg_fit_score", "duration_minutes"):
        val = summary.get(key)
        if val is not None:
            label = key.replace("_", " ").title()
            print(f"  ║  {label:<22} {str(val):>7}  ║")
    print("  ╚══════════════════════════════════╝")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="CLI test for JobHunter sessions")
    parser.add_argument("--env", choices=["production", "staging", "local"], default="production")
    parser.add_argument("--resume", default=DEFAULT_RESUME, help="Path to resume PDF")
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--keywords", nargs="+", default=None, help="Override keywords (default: from resume analysis)")
    parser.add_argument("--remote", action="store_true", default=True, help="Remote only (default: true)")
    parser.add_argument("--no-remote", action="store_true", help="Disable remote-only filter")
    parser.add_argument("--max-jobs", type=int, default=10)
    parser.add_argument("--boards", nargs="+", default=["linkedin", "indeed", "glassdoor"])
    parser.add_argument("--skip-coaching", action="store_true", help="Auto-approve coaching immediately")
    parser.add_argument("--skip-shortlist", action="store_true", help="Auto-approve shortlist immediately")
    parser.add_argument("--monitor-only", help="Just monitor an existing session ID")
    args = parser.parse_args()

    if args.no_remote:
        args.remote = False

    env = ENVS[args.env]
    base_url = env["api"]
    secret = env["secret"]

    print(f"🔧 Environment: {args.env}")
    print(f"🌐 API: {base_url}")

    # Mint auth token
    token = mint_jwe(args.email, secret)
    print(f"🔑 Auth token minted for {args.email}")

    # Monitor-only mode
    if args.monitor_only:
        monitor_session(base_url, token, args.monitor_only)
        return

    # Upload resume
    if not os.path.exists(args.resume):
        print(f"❌ Resume not found: {args.resume}")
        sys.exit(1)

    print(f"📄 Uploading resume: {args.resume}")
    resume_data = upload_resume(base_url, token, args.resume)
    resume_text = resume_data["text"]
    resume_file_path = resume_data["file_path"]
    print(f"  ✓ Parsed {len(resume_text)} chars, saved to {resume_file_path}")

    # Use provided keywords or default
    keywords = args.keywords or ["Senior Software Engineer", "Full-Stack Engineer", "AI Engineer"]

    print(f"🔑 Keywords: {keywords}")
    print(f"🌍 Remote only: {args.remote}")
    print(f"📋 Boards: {args.boards}")
    print(f"📊 Max jobs: {args.max_jobs}")

    # Create session
    print("\n🚀 Creating session...")
    session_id = create_session(
        base_url, token, resume_text, resume_file_path,
        keywords=keywords,
        remote_only=args.remote,
        max_jobs=args.max_jobs,
        job_boards=args.boards,
    )
    print(f"  ✓ Session created: {session_id}")

    # Monitor and auto-approve
    monitor_session(
        base_url, token, session_id,
        auto_approve_coaching=True,
        auto_approve_shortlist=args.skip_shortlist,
    )


if __name__ == "__main__":
    main()
