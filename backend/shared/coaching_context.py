"""Trusted, per-request temporal context for resume coaching."""
from datetime import datetime, timezone


def coaching_date_context() -> str:
    # Evaluate at invocation time, not import time in a long-lived worker.
    today = datetime.now(timezone.utc).date().isoformat()
    return f"""Current date (UTC): {today}.
Use this date when assessing resume chronology, not your training cutoff or a
previous coaching report. Dates earlier than today are not future dates.
Preserve the resume’s original dates; do not invent replacement dates or alter
them to resolve an assumed inconsistency. If chronology is genuinely ambiguous
or future-dated relative to today, ask the user to clarify instead of guessing.
A date concern in prior coached output is not authoritative evidence.
"""
