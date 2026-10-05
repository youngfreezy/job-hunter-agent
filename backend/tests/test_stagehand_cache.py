import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from stagehand import CacheMetadata

from backend.browser.stagehand_cache import (
    record_result_cache,
    result_cache_summary,
    routine_cache_options,
)


def result_with_cache(**metadata):
    return SimpleNamespace(metadata=SimpleNamespace(cache=CacheMetadata.model_validate(metadata)))


def test_routine_cache_explicitly_enables_first_repeat_reuse():
    assert routine_cache_options() == {'threshold': 1}


def test_operator_can_disable_result_caching(monkeypatch):
    from backend.shared.config import settings
    monkeypatch.setattr(settings, 'STAGEHAND_CACHE_ENABLED', False)
    assert routine_cache_options() is False


@pytest.mark.parametrize('flags', [{'fresh': True}, {'credentials': True}, {'fresh': True, 'credentials': True}])
def test_current_review_and_credentials_bypass_result_cache(flags):
    assert routine_cache_options(**flags) is False


def test_result_hits_count_saved_inference_separately_from_provider_prompt_cache(caplog, monkeypatch):
    # Integration fixtures run Alembic, whose logging configuration disables existing loggers.
    monkeypatch.setattr(logging.getLogger('backend.browser.stagehand_cache'), 'disabled', False)
    agent = SimpleNamespace()
    with caplog.at_level(logging.INFO, logger='backend.browser.stagehand_cache'):
        hit = record_result_cache(agent, 'observe', result_with_cache(
            status='HIT', count=2, threshold=1,
            tokens_saved={'input_tokens': 1200, 'output_tokens': 80, 'total_tokens': 1280},
        ))
        record_result_cache(agent, 'extract', result_with_cache(status='MISS', miss_reason='threshold', count=1, threshold=2))
        disabled = result_with_cache(status='DISABLED')
        disabled.metadata.usage = SimpleNamespace(cached_input_tokens=9000)
        record_result_cache(agent, 'observe', disabled)
    assert hit == {'operation': 'observe', 'status': 'HIT', 'count': 2, 'threshold': 1,
                   'saved_input_tokens': 1200, 'saved_output_tokens': 80}
    assert result_cache_summary(agent) == {
        'requests': 3, 'hits': 1, 'misses': 1, 'disabled': 1,
        'saved_input_tokens': 1200, 'saved_output_tokens': 80,
        'miss_reasons': {'threshold': 1},
    }
    assert 'HIT' in caplog.text


def test_logs_and_aggregate_cannot_include_untrusted_payload(caplog, monkeypatch):
    monkeypatch.setattr(logging.getLogger('backend.browser.stagehand_cache'), 'disabled', False)
    secret = 'alice@example.com https://example.com/application?token=private'
    agent = SimpleNamespace()
    result = SimpleNamespace(
        data={'arguments': [secret], 'instruction': secret},
        metadata=SimpleNamespace(cache=SimpleNamespace(
            status='MISS', miss_reason=secret, count=secret, threshold=True,
            tokens_saved=SimpleNamespace(input_tokens=1200, output_tokens=80),
        )),
    )
    with caplog.at_level(logging.INFO, logger='backend.browser.stagehand_cache'):
        record = record_result_cache(agent, 'observe', result)
        assert record_result_cache(agent, secret, result) is None
    assert record == {'operation': 'observe', 'status': 'MISS', 'miss_reason': 'unknown'}
    assert result_cache_summary(agent)['saved_input_tokens'] == 0
    assert result_cache_summary(agent)['miss_reasons'] == {'unknown': 1}
    assert '"miss_reason": "unknown"' in caplog.text
    assert secret not in caplog.text
    assert secret not in repr(result_cache_summary(agent))


@pytest.mark.parametrize('malformed', [None, {}, MagicMock(), SimpleNamespace(metadata=None),
                                    SimpleNamespace(metadata={'cache': {'status': ['HIT']}})])
def test_absent_or_malformed_metadata_does_not_break_the_application(malformed):
    agent = MagicMock()
    assert record_result_cache(agent, 'observe', malformed) is None
    assert result_cache_summary(agent)['requests'] == 0


def test_saved_token_values_are_bounded_and_non_boolean():
    agent = SimpleNamespace()
    record = record_result_cache(agent, 'observe', {
        'metadata': {'cache': {'status': 'HIT', 'count': -1, 'threshold': 0,
                               'tokens_saved': {'input_tokens': True, 'output_tokens': 10**30}}},
    })
    assert record == {'operation': 'observe', 'status': 'HIT',
                      'saved_input_tokens': 0, 'saved_output_tokens': 0}
    assert result_cache_summary(agent)['saved_input_tokens'] == 0


def test_cache_totals_are_isolated_per_browser_and_returned_as_copies():
    first, second = MagicMock(), SimpleNamespace()
    record_result_cache(first, 'extract', result_with_cache(status='MISS', miss_reason='not_found'))
    summary = result_cache_summary(first)
    summary['miss_reasons']['not_found'] = 500
    assert result_cache_summary(first)['miss_reasons'] == {'not_found': 1}
    assert result_cache_summary(second)['requests'] == 0
