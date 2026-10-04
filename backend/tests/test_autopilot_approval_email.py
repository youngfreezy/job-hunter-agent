from unittest.mock import AsyncMock
from html import unescape
import re

import pytest
from backend.shared import email_notifications


@pytest.mark.asyncio
async def test_approval_email_opens_review_without_token_or_automatic_action(monkeypatch):
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(email_notifications, 'send_email', sender)
    session_id = '0e3df91d-92ce-47b1-9dbb-c37a6a3809ba'
    assert await email_notifications.send_autopilot_approval_email(
        'fixture@example.test', session_id, 'schedule-fixture', 3, 'fixture-secret-token'
    )
    _, subject, html = sender.call_args.args
    assert subject == 'Autopilot: 3 jobs to review'
    links = [unescape(x) for x in re.findall(r'href="([^"]+)"', html)]
    assert links == [f'https://jobhunteragent.com/session/{session_id}']
    assert 'fixture-secret-token' not in html
    assert '/api/autopilot/approve' not in html
    assert 'matching your criteria' not in html
    assert 'Approve &amp; Apply' not in html
    assert 'expires in 24 hours' not in html
    assert 'Opening this link does not send applications.' in html


@pytest.mark.asyncio
async def test_review_link_cannot_escape_its_session_path(monkeypatch):
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(email_notifications, 'send_email', sender)
    await email_notifications.send_autopilot_approval_email(
        'fixture@example.test', 'id/extra?next=https://example.test&x="', 'schedule', 1, 'secret'
    )
    html = sender.call_args.args[2]
    links = re.findall(r'href="([^"]+)"', html)
    assert len(links) == 1
    assert links[0].startswith('https://jobhunteragent.com/session/id%2Fextra%3F')
    assert 'secret' not in html
