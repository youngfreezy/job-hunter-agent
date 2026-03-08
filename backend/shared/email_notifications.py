# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Email notification helpers using the Resend REST API."""

from __future__ import annotations

import logging
from html import escape

import httpx

from backend.shared.config import get_settings

logger = logging.getLogger(__name__)

_RESEND_API_URL = "https://api.resend.com/emails"
_FROM_ADDRESS = "JobHunter Agent <notifications@jobhunteragent.com>"


# ---------------------------------------------------------------------------
# Low-level sender
# ---------------------------------------------------------------------------

async def send_email(to: str, subject: str, html: str) -> bool:
    """Send an email via the Resend HTTP API.

    Returns ``True`` on success, ``False`` on failure (missing key, API error).
    """
    api_key = get_settings().RESEND_API_KEY
    if not api_key:
        logger.warning("RESEND_API_KEY is not configured — skipping email to %s", to)
        return False

    payload = {
        "from": _FROM_ADDRESS,
        "to": [to],
        "subject": subject,
        "html": html,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _RESEND_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if resp.status_code >= 400:
            logger.error(
                "Resend API error %s: %s",
                resp.status_code,
                resp.text,
            )
            return False
        logger.info("Email sent to %s — subject: %s", to, subject)
        return True
    except httpx.HTTPError as exc:
        logger.error("Failed to send email to %s: %s", to, exc)
        return False


# ---------------------------------------------------------------------------
# Session-complete notification
# ---------------------------------------------------------------------------

_SESSION_COMPLETE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background-color:#f4f4f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f7;padding:40px 0;">
    <tr>
      <td align="center">
        <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
          <!-- Header -->
          <tr>
            <td style="background-color:#1a1a2e;padding:28px 32px;">
              <h1 style="margin:0;color:#ffffff;font-size:20px;font-weight:600;">JobHunter Agent</h1>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding:32px;">
              <h2 style="margin:0 0 8px;font-size:22px;color:#1a1a2e;">Session Complete</h2>
              <p style="margin:0 0 24px;color:#6b7280;font-size:14px;">Here's a summary of your latest job search run.</p>

              <!-- Stats row -->
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
                <tr>
                  <td width="33%" style="text-align:center;padding:16px 8px;background-color:#f0fdf4;border-radius:6px;">
                    <div style="font-size:28px;font-weight:700;color:#16a34a;">{total_applied}</div>
                    <div style="font-size:12px;color:#6b7280;margin-top:4px;">Applied</div>
                  </td>
                  <td width="8"></td>
                  <td width="33%" style="text-align:center;padding:16px 8px;background-color:#fef2f2;border-radius:6px;">
                    <div style="font-size:28px;font-weight:700;color:#dc2626;">{total_failed}</div>
                    <div style="font-size:12px;color:#6b7280;margin-top:4px;">Failed</div>
                  </td>
                  <td width="8"></td>
                  <td width="33%" style="text-align:center;padding:16px 8px;background-color:#fffbeb;border-radius:6px;">
                    <div style="font-size:28px;font-weight:700;color:#d97706;">{total_skipped}</div>
                    <div style="font-size:12px;color:#6b7280;margin-top:4px;">Skipped</div>
                  </td>
                </tr>
              </table>

              <!-- Time Saved highlight -->
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
                <tr>
                  <td style="text-align:center;padding:20px;background-color:#ecfdf5;border-radius:8px;border:1px solid #a7f3d0;">
                    <div style="font-size:36px;font-weight:700;color:#059669;">{time_saved}</div>
                    <div style="font-size:14px;color:#065f46;margin-top:4px;">of manual work saved this session</div>
                  </td>
                </tr>
              </table>

              <!-- Details -->
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;border:1px solid #e5e7eb;border-radius:6px;overflow:hidden;">
                <tr>
                  <td style="padding:12px 16px;border-bottom:1px solid #e5e7eb;font-size:14px;color:#6b7280;">Avg Fit Score</td>
                  <td style="padding:12px 16px;border-bottom:1px solid #e5e7eb;font-size:14px;font-weight:600;color:#1a1a2e;text-align:right;">{avg_fit_score}%</td>
                </tr>
                <tr>
                  <td style="padding:12px 16px;border-bottom:1px solid #e5e7eb;font-size:14px;color:#6b7280;">Duration</td>
                  <td style="padding:12px 16px;border-bottom:1px solid #e5e7eb;font-size:14px;font-weight:600;color:#1a1a2e;text-align:right;">{duration}</td>
                </tr>
                <tr>
                  <td style="padding:12px 16px;font-size:14px;color:#6b7280;">Top Companies</td>
                  <td style="padding:12px 16px;font-size:14px;font-weight:600;color:#1a1a2e;text-align:right;">{top_companies}</td>
                </tr>
              </table>

              <!-- CTA -->
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td align="center">
                    <a href="/session/{session_id}" style="display:inline-block;padding:12px 28px;background-color:#1a1a2e;color:#ffffff;font-size:14px;font-weight:600;text-decoration:none;border-radius:6px;">View Full Results</a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding:20px 32px;background-color:#f9fafb;border-top:1px solid #e5e7eb;">
              <p style="margin:0;font-size:12px;color:#9ca3af;text-align:center;">You received this email because a job search session completed on your JobHunter Agent account.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def _format_duration(minutes: float) -> str:
    """Return a human-friendly duration string."""
    if minutes < 1:
        return f"{minutes * 60:.0f}s"
    if minutes < 60:
        return f"{minutes:.0f}m"
    hours = int(minutes // 60)
    remaining = int(minutes % 60)
    return f"{hours}h {remaining}m"


_MANUAL_MINUTES_PER_APP = 60  # HR Dive + BLS benchmark


async def send_session_complete_email(
    to_email: str,
    session_id: str,
    total_applied: int,
    total_failed: int,
    total_skipped: int,
    top_companies: list[str],
    avg_fit_score: float,
    duration_minutes: float,
) -> bool:
    """Send a summary email when a job-search session finishes."""
    subject = f"Your job search session is complete — {total_applied} applications sent"

    companies_str = ", ".join(escape(c) for c in top_companies) if top_companies else "—"

    # Time saved: what manual work would have taken minus automation time
    manual_estimate = total_applied * _MANUAL_MINUTES_PER_APP
    time_saved_minutes = max(0, manual_estimate - duration_minutes)
    time_saved_str = _format_duration(time_saved_minutes)

    html = _SESSION_COMPLETE_TEMPLATE.format(
        total_applied=total_applied,
        total_failed=total_failed,
        total_skipped=total_skipped,
        avg_fit_score=f"{avg_fit_score:.1f}",
        duration=_format_duration(duration_minutes),
        top_companies=companies_str,
        session_id=escape(session_id),
        time_saved=time_saved_str,
    )

    return await send_email(to_email, subject, html)


# ---------------------------------------------------------------------------
# Autopilot session started notification
# ---------------------------------------------------------------------------

_AUTOPILOT_STARTED_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background-color:#f4f4f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f7;padding:40px 0;">
    <tr>
      <td align="center">
        <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
          <!-- Header -->
          <tr>
            <td style="background-color:#1e40af;padding:28px 32px;">
              <h1 style="margin:0;color:#ffffff;font-size:20px;font-weight:600;">JobHunter Agent — Autopilot</h1>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding:32px;">
              <h2 style="margin:0 0 8px;font-size:22px;color:#1a1a2e;">Autopilot Session Started</h2>
              <p style="margin:0 0 24px;color:#6b7280;font-size:14px;">Your scheduled search <strong>{schedule_name}</strong> is running.</p>

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;border:1px solid #e5e7eb;border-radius:6px;overflow:hidden;">
                <tr>
                  <td style="padding:12px 16px;border-bottom:1px solid #e5e7eb;font-size:14px;color:#6b7280;">Keywords</td>
                  <td style="padding:12px 16px;border-bottom:1px solid #e5e7eb;font-size:14px;font-weight:600;color:#1a1a2e;text-align:right;">{keywords}</td>
                </tr>
                <tr>
                  <td style="padding:12px 16px;font-size:14px;color:#6b7280;">Session</td>
                  <td style="padding:12px 16px;font-size:14px;font-weight:600;color:#1a1a2e;text-align:right;">{session_id_short}</td>
                </tr>
              </table>

              <p style="margin:0 0 24px;color:#6b7280;font-size:14px;">You'll receive another email when the session completes with a summary of discovered jobs. If approval is required, you can review and approve directly from that email.</p>

              <!-- CTA -->
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td align="center">
                    <a href="/session/{session_id}" style="display:inline-block;padding:12px 28px;background-color:#1a1a2e;color:#ffffff;font-size:14px;font-weight:600;text-decoration:none;border-radius:6px;">Watch Live</a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding:20px 32px;background-color:#f9fafb;border-top:1px solid #e5e7eb;">
              <p style="margin:0;font-size:12px;color:#9ca3af;text-align:center;">This autopilot session was triggered by your scheduled search on JobHunter Agent.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


async def send_autopilot_started_email(
    to_email: str,
    session_id: str,
    schedule_name: str,
    keywords: list[str],
) -> bool:
    """Send a notification when an autopilot session starts."""
    subject = f"Autopilot running — {schedule_name}"
    keywords_str = ", ".join(escape(k) for k in keywords) if keywords else "—"

    html = _AUTOPILOT_STARTED_TEMPLATE.format(
        schedule_name=escape(schedule_name),
        keywords=keywords_str,
        session_id=escape(session_id),
        session_id_short=escape(session_id[:8]),
    )

    return await send_email(to_email, subject, html)


# ---------------------------------------------------------------------------
# Failed-application notification
# ---------------------------------------------------------------------------

_APPLICATION_FAILED_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background-color:#f4f4f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f7;padding:40px 0;">
    <tr>
      <td align="center">
        <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
          <!-- Header -->
          <tr>
            <td style="background-color:#7f1d1d;padding:28px 32px;">
              <h1 style="margin:0;color:#ffffff;font-size:20px;font-weight:600;">JobHunter Agent</h1>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding:32px;">
              <h2 style="margin:0 0 8px;font-size:22px;color:#1a1a2e;">Application Failed</h2>
              <p style="margin:0 0 24px;color:#6b7280;font-size:14px;">An application could not be completed. Details below.</p>

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;border:1px solid #e5e7eb;border-radius:6px;overflow:hidden;">
                <tr>
                  <td style="padding:12px 16px;border-bottom:1px solid #e5e7eb;font-size:14px;color:#6b7280;">Job Title</td>
                  <td style="padding:12px 16px;border-bottom:1px solid #e5e7eb;font-size:14px;font-weight:600;color:#1a1a2e;text-align:right;">{job_title}</td>
                </tr>
                <tr>
                  <td style="padding:12px 16px;border-bottom:1px solid #e5e7eb;font-size:14px;color:#6b7280;">Company</td>
                  <td style="padding:12px 16px;border-bottom:1px solid #e5e7eb;font-size:14px;font-weight:600;color:#1a1a2e;text-align:right;">{company}</td>
                </tr>
                <tr>
                  <td style="padding:12px 16px;font-size:14px;color:#6b7280;">Error</td>
                  <td style="padding:12px 16px;font-size:14px;color:#dc2626;text-align:right;">{error_reason}</td>
                </tr>
              </table>

              <!-- CTA -->
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td align="center">
                    <a href="/session/{session_id}" style="display:inline-block;padding:12px 28px;background-color:#1a1a2e;color:#ffffff;font-size:14px;font-weight:600;text-decoration:none;border-radius:6px;">View Session</a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding:20px 32px;background-color:#f9fafb;border-top:1px solid #e5e7eb;">
              <p style="margin:0;font-size:12px;color:#9ca3af;text-align:center;">You received this email because an application failed during your JobHunter Agent session.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


async def send_application_failed_email(
    to_email: str,
    session_id: str,
    job_title: str,
    company: str,
    error_reason: str,
) -> bool:
    """Send a notification when a single application fails."""
    subject = f"Application failed — {job_title} at {company}"

    html = _APPLICATION_FAILED_TEMPLATE.format(
        job_title=escape(job_title),
        company=escape(company),
        error_reason=escape(error_reason),
        session_id=escape(session_id),
    )

    return await send_email(to_email, subject, html)
