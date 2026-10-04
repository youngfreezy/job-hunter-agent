"""Real Postgres regression for legacy strategy tables, without model calls."""
from contextlib import contextmanager
import uuid

import psycopg
from psycopg import sql
import pytest

from backend.optimization import application_feedback as feedback
from backend.shared.config import get_settings

pytestmark = pytest.mark.requires_postgres


@pytest.fixture
def isolated_strategy_table(monkeypatch):
    schema = 'test_feedback_' + uuid.uuid4().hex
    conn = psycopg.connect(get_settings().DATABASE_URL)
    conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
    conn.commit()

    class Pool:
        @contextmanager
        def connection(self):
            yield conn

    monkeypatch.setattr(feedback, 'get_pool', lambda: Pool())
    monkeypatch.setattr(feedback, '_TABLE_ENSURED', False)
    try:
        yield conn
    finally:
        conn.rollback()
        conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        conn.commit()
        conn.close()


@pytest.mark.parametrize('legacy', [True, False])
def test_initialization_repairs_legacy_schema_and_refresh_persists(isolated_strategy_table, monkeypatch, legacy):
    conn = isolated_strategy_table
    if legacy:
        conn.execute('''CREATE TABLE ats_strategies (
            ats_type TEXT PRIMARY KEY, strategy_tip TEXT NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT NOW())''')
        conn.execute("INSERT INTO ats_strategies (ats_type, strategy_tip) VALUES ('indeed', 'preserve original tip')")
        conn.commit()
    feedback._ensure_table()
    if legacy:
        assert feedback.get_ats_tips('indeed') == 'preserve original tip'
    # Repeat after a simulated process restart; migrations must be idempotent.
    monkeypatch.setattr(feedback, '_TABLE_ENSURED', False)
    feedback._ensure_table()
    stats = {'total': 5, 'submitted': 1, 'failed': 4, 'success_rate': 0.2,
             'top_errors': {'timeout': 4}, 'top_failure_steps': {'read': 4}}
    monkeypatch.setattr(feedback, 'analyze_ats_outcomes', lambda: {'indeed': stats})
    monkeypatch.setattr(feedback, '_generate_strategy_with_llm', lambda *_: 'fixture strategy')
    assert feedback.refresh_all_strategies() == 1
    row = conn.execute('''SELECT strategy_tip, success_rate, total_attempts,
        top_errors, top_failure_steps FROM ats_strategies WHERE ats_type='indeed' ''').fetchone()
    assert row == ('fixture strategy', 0.2, 5, {'timeout': 4}, {'read': 4})
    assert feedback.refresh_all_strategies() == 1
    assert conn.execute('SELECT COUNT(*) FROM ats_strategies').fetchone()[0] == 1


def test_budget_refresh_still_persists_statistics_without_model(isolated_strategy_table, monkeypatch, tmp_path):
    from backend.shared import llm
    from unittest.mock import Mock
    conn = isolated_strategy_table
    monkeypatch.setenv('JOBHUNTER_MODEL_BUDGET_LEDGER', str(tmp_path/'not-opened.sqlite'))
    build = Mock(side_effect=AssertionError('No model call'))
    monkeypatch.setattr(llm, 'build_llm', build)
    stats = {'total': 5, 'submitted': 1, 'failed': 4, 'success_rate': 0.2,
             'top_errors': {'timeout': 4}, 'top_failure_steps': {'read': 4}}
    monkeypatch.setattr(feedback, 'analyze_ats_outcomes', lambda: {'indeed': stats})
    assert feedback.refresh_all_strategies() == 1
    row = conn.execute('SELECT success_rate, total_attempts, strategy_tip FROM ats_strategies').fetchone()
    assert row[:2] == (0.2, 5)
    assert '20%' in row[2] and 'slow-loading' in row[2]
    build.assert_not_called()
