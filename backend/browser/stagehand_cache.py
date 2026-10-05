"""Explicit Stagehand result caching and diagnostics without applicant content."""
from dataclasses import dataclass, field
import json
import logging
import re
from urllib.parse import urlsplit

from stagehand import CacheOptions
from backend.shared.config import settings

logger = logging.getLogger(__name__)
_OPERATIONS = frozenset({'act', 'observe', 'extract'})
_STATUSES = {'HIT': 'hits', 'MISS': 'misses', 'DISABLED': 'disabled'}
_MISS_REASONS = frozenset({
    'not_found', 'threshold', 'empty_array', 'timeout', 'error', 'bypass',
    'screenshot', 'not_enabled', 'no_cache_key', 'read_failed', 'replay_failed', 'unknown',
})
_MAX_VALUE = 1_000_000_000
_STATS_ATTRIBUTE = '_jobhunter_result_cache_stats'


def routine_cache_options(*, fresh: bool = False, credentials: bool = False) -> CacheOptions | bool:
    """Opt in explicitly; current final reviews and credential flows stay fresh."""
    return False if fresh or credentials or not settings.STAGEHAND_CACHE_ENABLED else CacheOptions(threshold=1)


async def page_cache_options(page, instruction: str = '', *, fresh: bool = False):
    """Keep credential forms and instructions out of the provider's result cache."""
    if routine_cache_options(fresh=fresh) is False:
        return False
    sensitive = bool(re.search(
        r'\b(password|passcode|otp|verification code|security code|one[- ]time code|api[ _-]?key|access[ _-]?token)\b',
        instruction, re.I)) or bool(re.search(
            r'/(?:auth|login|signin|sign-in|oauth|account/verify)(?:/|$)',
            urlsplit(await page.url()).path, re.I))
    sensitive = sensitive or bool(await page.locator(
        'input[type="password"], input[autocomplete="one-time-code"], '
        'input[autocomplete="current-password"], input[autocomplete="new-password"]',
    ).count())
    return routine_cache_options(credentials=sensitive)


def _field(value, name):
    # Do not invoke properties or MagicMock's dynamically generated attributes.
    if isinstance(value, dict):
        return value.get(name)
    try:
        return vars(value).get(name)
    except TypeError:
        return None


def _integer(value, minimum=0):
    return value if type(value) is int and minimum <= value <= _MAX_VALUE else None


@dataclass
class _CacheStats:
    counts: dict[str, int] = field(default_factory=lambda: {'hits': 0, 'misses': 0, 'disabled': 0})
    saved_input_tokens: int = 0
    saved_output_tokens: int = 0
    miss_reasons: dict[str, int] = field(default_factory=dict)


def record_result_cache(agent, operation: str, result) -> dict | None:
    """Record only bounded, allowlisted SDK cache metadata, never result data."""
    if not isinstance(operation, str) or operation not in _OPERATIONS:
        return None
    cache = _field(_field(result, 'metadata'), 'cache')
    status = _field(cache, 'status')
    if not isinstance(status, str) or status not in _STATUSES:
        return None
    stats = _field(agent, _STATS_ATTRIBUTE)
    if not isinstance(stats, _CacheStats):
        stats = _CacheStats()
        setattr(agent, _STATS_ATTRIBUTE, stats)
    record = {'operation': operation, 'status': str(status)}
    key = _STATUSES[status]
    stats.counts[key] = min(_MAX_VALUE, stats.counts[key] + 1)
    if status != 'DISABLED':
        for name, minimum in (('count', 0), ('threshold', 1)):
            value = _integer(_field(cache, name), minimum)
            if value is not None:
                record[name] = value
    if status == 'HIT':
        tokens = _field(cache, 'tokens_saved')
        for kind in ('input', 'output'):
            value = _integer(_field(tokens, f'{kind}_tokens')) or 0
            name = f'saved_{kind}_tokens'
            record[name] = value
            setattr(stats, name, min(_MAX_VALUE, getattr(stats, name) + value))
    elif status == 'MISS':
        reason = _field(cache, 'miss_reason')
        reason = reason if isinstance(reason, str) and reason in _MISS_REASONS else 'unknown'
        record['miss_reason'] = reason
        stats.miss_reasons[reason] = min(_MAX_VALUE, stats.miss_reasons.get(reason, 0) + 1)
    logger.info('Stagehand result cache %s', json.dumps(record, sort_keys=True))
    return record


def result_cache_summary(agent) -> dict:
    """Return independent counters for logs/UI; these are not provider prompt-cache tokens."""
    stats = _field(agent, _STATS_ATTRIBUTE)
    if not isinstance(stats, _CacheStats):
        stats = _CacheStats()
    return {
        'requests': sum(stats.counts.values()), **stats.counts,
        'saved_input_tokens': stats.saved_input_tokens,
        'saved_output_tokens': stats.saved_output_tokens,
        'miss_reasons': dict(stats.miss_reasons),
    }
