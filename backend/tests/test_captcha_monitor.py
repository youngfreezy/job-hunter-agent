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
