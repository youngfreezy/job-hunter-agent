import builtins
import pytest
from types import SimpleNamespace
from unittest.mock import Mock

from backend.optimization import evolve


def test_budget_mode_blocks_optional_optimizer_before_dependency_or_outcome_work(monkeypatch):
    monkeypatch.setenv('JOBHUNTER_MODEL_BUDGET_LEDGER', '/offline/not-opened.sqlite')
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        assert not name.startswith('evoagentx'), 'Budget mode must stop before optional SDK initialization'
        assert name != 'backend.shared.outcome_store', 'Budget mode must stop before database reads'
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded_import)
    result = evolve.run_optimization()
    assert result['error'] == 'budget_mode'


def test_optimizer_models_follow_settings_without_unsupported_sampling(monkeypatch):
    from backend.shared import config

    monkeypatch.setattr(config, 'get_settings', lambda: SimpleNamespace(
        ANTHROPIC_LIGHT_MODEL='claude-haiku-4-5-20251001',
        ANTHROPIC_DEFAULT_MODEL='claude-sonnet-5-5',
    ))
    factory = Mock(side_effect=lambda **kwargs: kwargs)
    executor, optimizer = evolve._model_configs(factory, 'offline-test-key')
    assert executor['model'] == 'anthropic/claude-haiku-4-5-20251001'
    assert optimizer['model'] == 'anthropic/claude-sonnet-5-5'
    for settings in (executor, optimizer):
        assert settings['anthropic_key'] == 'offline-test-key'
        assert settings['temperature'] is None
        assert settings['top_p'] is None
        assert settings['tool_choice'] is None


def test_invalid_budget_configuration_also_fails_closed(monkeypatch):
    from backend.shared.model_budget import BudgetStopped

    monkeypatch.setenv('JOBHUNTER_MODEL_BUDGET_LEDGER', '')
    with pytest.raises(BudgetStopped):
        evolve.run_optimization()
