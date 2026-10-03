from unittest.mock import AsyncMock

import pytest

from backend.shared import email_notifications


@pytest.mark.asyncio
@pytest.mark.parametrize("applied", [0, 2])
async def test_completion_email_describes_actual_submission_outcome(monkeypatch, applied):
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(email_notifications, "send_email", send)
    await email_notifications.send_session_complete_email(
        "test@example.com", "test-session", applied, 0, 0, [], 0, 5,
    )
    _, subject, html = send.await_args.args
    if applied == 0:
        assert "without submitting any applications" in subject
        assert "No applications submitted" in html
        assert "Session Complete" not in html
    else:
        assert "2 applications sent" in subject
        assert "Session Complete" in html
