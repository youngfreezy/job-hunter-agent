"""Optional background learning must not spend the application demo budget."""
from unittest.mock import Mock

import pytest

from backend.optimization import application_feedback as feedback
from backend.shared import llm
from backend.shared.model_budget import BudgetStopped


def _stats():
    return {'total': 5, 'submitted': 1, 'failed': 4, 'success_rate': 0.2,
            'top_errors': {'timeout': 4}, 'top_failure_steps': {'read': 4}}


def test_budget_mode_uses_rule_based_tip_before_constructing_model(monkeypatch, tmp_path):
    monkeypatch.setenv('JOBHUNTER_MODEL_BUDGET_LEDGER', str(tmp_path/'not-opened.sqlite'))
    build = Mock(side_effect=AssertionError('No paid strategy model may be constructed'))
    monkeypatch.setattr(llm, 'build_llm', build)
    tip = feedback._generate_strategy_with_llm('indeed', _stats())
    assert '20%' in tip and 'slow-loading' in tip
    build.assert_not_called()


def test_normal_mode_still_generates_strategy(monkeypatch):
    monkeypatch.delenv('JOBHUNTER_MODEL_BUDGET_LEDGER', raising=False)
    client = Mock()
    client.invoke.return_value.content = 'Grounded strategy tip'
    build = Mock(return_value=client)
    monkeypatch.setattr(llm, 'build_llm', build)
    assert feedback._generate_strategy_with_llm('indeed', _stats()) == 'Grounded strategy tip'
    build.assert_called_once()


def test_invalid_budget_configuration_never_calls_strategy_model(monkeypatch):
    monkeypatch.setenv('JOBHUNTER_MODEL_BUDGET_LEDGER', '')
    build = Mock()
    monkeypatch.setattr(llm, 'build_llm', build)
    with pytest.raises(BudgetStopped):
        feedback._generate_strategy_with_llm('indeed', _stats())
    build.assert_not_called()
