"""Local, persistent ceiling for the explicitly budgeted Sonnet demo.

Only standard Sonnet 5.5 inference is supported. Reserve its entire 1M input
context plus maximum output before dispatch, then settle provider-reported usage.
No prompt/token estimate is trusted as a ceiling. Unknown outcomes retain their
reservation. Browserbase and API consumers outside this process are NOT covered.

Pricing: https://platform.claude.com/docs/en/about-claude/pricing
Context: https://platform.claude.com/docs/en/models/sonnet-5-5/overview
"""
from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
import json
import os
from pathlib import Path
import sqlite3
import uuid

from backend.shared.anthropic_compat import CompatibleChatAnthropic

# Fixed reviewed model ID and standard rates; no automatic model fallback.
MODEL = 'claude-sonnet-5-5'
INPUT_LIMIT = 1_000_000
OUTPUT_LIMIT = 128_000
# Integer millionths of a dollar per token; no floating point accounting.
INPUT_RATE = 2
OUTPUT_RATE = 10


class BudgetStopped(RuntimeError):
    """Do not dispatch another paid request without a valid reservation."""


def configured_ledger() -> str | None:
    value = os.environ.get('JOBHUNTER_MODEL_BUDGET_LEDGER')
    if value is not None and (not value or not Path(value).is_absolute()):
        raise BudgetStopped('Model budget ledger must be an absolute, initialized file path.')
    return value


class Ledger:
    def __init__(self, path):
        self.path = Path(path)

    @classmethod
    def create(cls, path, *, limit_usd):
        """Explicit one-time initialization. Never replace an existing budget."""
        amount = Decimal(str(limit_usd)) * 1_000_000
        if not amount.is_finite() or amount <= 0 or amount != amount.to_integral_value():
            raise BudgetStopped('Budget must be positive whole microdollars.')
        path = Path(path)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
            with sqlite3.connect(path) as db:
                db.executescript('''
                    CREATE TABLE budget (id INTEGER PRIMARY KEY CHECK(id=1), ceiling INTEGER NOT NULL);
                    CREATE TABLE calls (id TEXT PRIMARY KEY, reserved INTEGER NOT NULL,
                        charged INTEGER, usage_json TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
                ''')
                db.execute('INSERT INTO budget VALUES (1, ?)', (int(amount),))
        except (OSError, sqlite3.Error) as exc:
            raise BudgetStopped('Cannot initialize model budget; existing ledgers are never reset.') from exc
        return cls(path)

    @contextmanager
    def _transaction(self):
        db = None
        try:
            # mode=rw must not create a missing ledger after a restart/path typo.
            db = sqlite3.connect(self.path.resolve().as_uri() + '?mode=rw', uri=True, timeout=10)
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except (OSError, sqlite3.Error) as exc:
            raise BudgetStopped('Model budget ledger is unavailable; paid request blocked.') from exc
        finally:
            if db is not None:
                db.close()

    @staticmethod
    def _snapshot(db):
        row = db.execute('SELECT ceiling FROM budget WHERE id=1').fetchone()
        if row is None or not isinstance(row[0], int) or row[0] <= 0:
            raise BudgetStopped('Invalid model budget ledger.')
        committed = db.execute('SELECT COALESCE(SUM(COALESCE(charged, reserved)), 0) FROM calls').fetchone()[0]
        return {'limit_microusd': row[0], 'committed_microusd': committed}

    def snapshot(self):
        with self._transaction() as db:
            return self._snapshot(db)

    def reserve(self, amount):
        if type(amount) is not int or amount <= 0:
            raise BudgetStopped('Invalid model reservation.')
        with self._transaction() as db:
            state = self._snapshot(db)
            if state['committed_microusd'] + amount > state['limit_microusd']:
                raise BudgetStopped('Model spend ceiling reached; paid request blocked.')
            key = str(uuid.uuid4())
            db.execute('INSERT INTO calls (id, reserved) VALUES (?, ?)', (key, amount))
        return key

    def settle(self, key, amount, usage):
        with self._transaction() as db:
            row = db.execute('SELECT reserved, charged FROM calls WHERE id=?', (key,)).fetchone()
            if row is None or row[1] is not None or type(amount) is not int or amount < 0 or amount > row[0]:
                raise BudgetStopped('Unverifiable usage; full reservation retained.')
            db.execute('UPDATE calls SET charged=?, usage_json=? WHERE id=?',
                       (amount, json.dumps(usage, sort_keys=True), key))


def _has_cache_control(value):
    if isinstance(value, dict):
        return 'cache_control' in value or any(_has_cache_control(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_cache_control(v) for v in value)
    return False


class BudgetChatAnthropic(CompatibleChatAnthropic):
    budget_ledger_path: str

    def _reserve(self, payload):
        # Reject unpriced server tools, caching, premium tiers and future options.
        allowed = {'model', 'max_tokens', 'messages', 'system', 'temperature', 'top_k',
                   'top_p', 'stop_sequences', 'tools', 'tool_choice', 'betas',
                   'output_format', 'output_config', 'service_tier', 'thinking'}
        if set(payload) - allowed or payload.get('model') != MODEL or _has_cache_control(payload):
            raise BudgetStopped('Request contains model features outside the approved budget.')
        output = payload.get('max_tokens')
        if type(output) is not int or not 0 < output <= OUTPUT_LIMIT:
            raise BudgetStopped('Unbounded model output is not permitted.')
        if payload.get('service_tier', 'standard_only') != 'standard_only':
            raise BudgetStopped('Only standard model pricing is permitted.')
        if any(tool.get('type', 'custom') != 'custom' for tool in payload.get('tools', [])):
            raise BudgetStopped('Paid server tools are not permitted in budget mode.')
        if set(payload.get('betas', [])) - {'structured-outputs-2025-11-13', 'effort-2025-11-24'}:
            raise BudgetStopped('Unpriced model beta is not permitted.')
        if self.max_retries != 0:
            raise BudgetStopped('Automatic provider retries must be disabled in budget mode.')
        payload['service_tier'] = 'standard_only'
        return Ledger(self.budget_ledger_path).reserve(INPUT_LIMIT * INPUT_RATE + output * OUTPUT_RATE)

    def _settle(self, reservation, payload, response):
        usage = getattr(response, 'usage', None)
        if usage is None:
            raise BudgetStopped('Provider usage missing; full reservation retained.')
        values = {name: getattr(usage, name, None) for name in ('input_tokens', 'output_tokens')}
        values.update({name: getattr(usage, name, 0) or 0 for name in
                       ('cache_creation_input_tokens', 'cache_read_input_tokens')})
        if any(type(value) is not int or value < 0 for value in values.values()):
            raise BudgetStopped('Provider usage invalid; full reservation retained.')
        if (values['input_tokens'] > INPUT_LIMIT or values['output_tokens'] > payload['max_tokens']
                or values['cache_creation_input_tokens'] or values['cache_read_input_tokens']):
            raise BudgetStopped('Unexpected provider billing; full reservation retained.')
        amount = values['input_tokens'] * INPUT_RATE + values['output_tokens'] * OUTPUT_RATE
        Ledger(self.budget_ledger_path).settle(reservation, amount, values)

    def _create(self, payload):
        reservation = self._reserve(payload)
        response = super()._create(payload)
        self._settle(reservation, payload, response)
        return response

    async def _acreate(self, payload):
        reservation = self._reserve(payload)
        response = await super()._acreate(payload)
        self._settle(reservation, payload, response)
        return response

    def _stream(self, *args, **kwargs):
        raise BudgetStopped('Streaming bypass is disabled in budget mode.')
        yield  # Preserve generator contract without any provider dispatch.

    async def _astream(self, *args, **kwargs):
        raise BudgetStopped('Streaming bypass is disabled in budget mode.')
        yield
