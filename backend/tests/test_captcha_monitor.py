import asyncio
import json

import pytest

from backend.browser.captcha_monitor import CaptchaMonitor


def signal(monitor, status, identifier='challenge-one'):
    monitor.record(json.dumps({'key': 'browserbase-captcha-event', 'status': status, 'id': identifier}))


@pytest.mark.asyncio
async def test_modern_events_wait_for_matching_finish_across_page_messages():
    monitor = CaptchaMonitor()
    signal(monitor, 'started')
    signal(monitor, 'finished', 'unrelated')
    assert monitor.active
    waiter = asyncio.create_task(monitor.wait_until_idle(timeout=1))
    await asyncio.sleep(0)
    assert not waiter.done()
    signal(monitor, 'finished')
    await waiter
    assert not monitor.active
    assert monitor.generation == 2
    signal(monitor, 'started')  # duplicate delivery cannot reopen a finished ID
    assert not monitor.active


@pytest.mark.asyncio
async def test_multiple_challenges_and_legacy_events_do_not_release_early():
    monitor = CaptchaMonitor()
    signal(monitor, 'started', 'a'); signal(monitor, 'started', 'b')
    signal(monitor, 'finished', 'a')
    with pytest.raises(TimeoutError):
        await monitor.wait_until_idle(timeout=0.001)
    signal(monitor, 'finished', 'b')
    monitor.record('browserbase-solving-started')
    assert monitor.active
    monitor.record('browserbase-solving-finished')
    await monitor.wait_until_idle(timeout=0.1)
    monitor.record('browserbase-solving-started')  # legacy can start again
    assert monitor.active


def test_unrelated_console_content_is_ignored():
    monitor = CaptchaMonitor()
    for message in ('hello', '{}', '[]', '{"key":"application","status":"finished"}'):
        monitor.record(message)
    assert not monitor.active
    assert monitor.generation == 0


def test_diagnostics_record_transitions_without_page_content_or_challenge_ids(caplog):
    monitor = CaptchaMonitor(session_id='test-browser-session')
    caplog.set_level('INFO', logger='backend.browser.captcha_monitor')
    private_id = 'private-challenge-value'
    signal(monitor, 'started', private_id)
    signal(monitor, 'started', private_id)  # duplicate delivery is not a transition
    signal(monitor, 'finished', 'unrelated')
    signal(monitor, 'finished', private_id)
    monitor.record('private-page-content')
    records = [r for r in caplog.records if r.name == 'backend.browser.captcha_monitor']
    assert len(records) == 2
    assert 'session=test-browser-session status=started generation=1 active=1' in records[0].getMessage()
    assert 'session=test-browser-session status=finished generation=2 active=0' in records[1].getMessage()
    assert private_id not in caplog.text
    assert 'private-page-content' not in caplog.text
