"""Read Browserbase solve events; never solve a challenge or operate a control."""
from __future__ import annotations

import asyncio
import json


class CaptchaMonitor:
    def __init__(self):
        self._active: set[str] = set()
        self._finished: set[str] = set()
        self.generation = 0
        self._idle = asyncio.Event()
        self._idle.set()

    @property
    def active(self) -> bool:
        return bool(self._active)

    def record(self, text: str) -> None:
        # Modern Browserbase events carry a challenge ID, even across page events.
        if text in ('browserbase-solving-started', 'browserbase-solving-finished'):
            challenge_id = 'legacy'
            status = 'started' if text.endswith('started') else 'finished'
        else:
            try:
                event = json.loads(text)
            except (TypeError, ValueError):
                return
            if not isinstance(event, dict) or event.get('key') != 'browserbase-captcha-event':
                return
            challenge_id, status = event.get('id'), event.get('status')
            if not isinstance(challenge_id, str) or not challenge_id:
                return
        if status == 'started':
            if challenge_id in self._active or (challenge_id != 'legacy' and challenge_id in self._finished):
                return
            self._active.add(challenge_id)
            self._idle.clear()
        elif status == 'finished':
            if challenge_id not in self._active:
                return  # An unrelated finish must not release another challenge.
            self._active.remove(challenge_id)
            self._finished.add(challenge_id)
            if not self._active:
                self._idle.set()
        else:
            return
        self.generation += 1

    async def wait_until_idle(self, timeout: float = 90) -> None:
        await asyncio.wait_for(self._idle.wait(), timeout=timeout)
