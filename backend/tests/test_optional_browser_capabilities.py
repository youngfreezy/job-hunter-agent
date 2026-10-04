"""Default runtime stays explicit about optional engines, without paid calls."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest
from backend.shared import optional_browser


def test_optional_browser_imports_only_when_requested(monkeypatch):
    module = SimpleNamespace(Agent=object(), Browser=object())
    load = MagicMock(return_value=module)
    monkeypatch.setattr(optional_browser, 'import_module', load)
    assert optional_browser.require_browser_use() is module
    load.assert_called_once_with('browser_use')


def test_missing_legacy_engine_is_a_sanitized_capability_error(monkeypatch):
    monkeypatch.setattr(optional_browser, 'import_module', MagicMock(side_effect=ModuleNotFoundError('private dependency path')))
    with pytest.raises(optional_browser.OptionalBrowserUnavailable, match='unavailable on this deployment') as error:
        optional_browser.require_browser_use()
    assert 'private dependency path' not in str(error.value)


@pytest.mark.asyncio
async def test_linkedin_without_optional_engine_refuses_before_background_work(monkeypatch):
    from backend.gateway.routes import sessions
    from backend.gateway import deps
    from fastapi import HTTPException
    monkeypatch.setattr(deps, 'get_model_user', lambda _: {'id': 'owner'})
    monkeypatch.setattr(deps, 'verify_session_owner', AsyncMock())
    monkeypatch.setattr(optional_browser, 'import_module', MagicMock(side_effect=ModuleNotFoundError()))
    spawn = MagicMock(); monkeypatch.setattr(sessions, '_spawn_background', spawn)
    emit = MagicMock(); monkeypatch.setattr(sessions, 'register_emitter', emit)
    with pytest.raises(HTTPException) as error:
        await sessions.start_linkedin_update('offline-session', sessions.LinkedInUpdateRequest(updates=[{'section':'headline','content':'Engineer'}]), None)
    assert error.value.status_code == 503
    spawn.assert_not_called()
    emit.assert_not_called()


@pytest.mark.asyncio
async def test_installed_optional_engine_keeps_linkedin_launch_contract(monkeypatch):
    from backend.gateway.routes import sessions
    from backend.gateway import deps
    monkeypatch.setattr(deps, 'get_model_user', lambda _: {'id': 'owner'})
    monkeypatch.setattr(deps, 'verify_session_owner', AsyncMock())
    monkeypatch.setattr(optional_browser, 'import_module', lambda _: SimpleNamespace())
    tasks = []
    monkeypatch.setattr(sessions, '_spawn_background', tasks.append)
    monkeypatch.setattr(sessions, 'register_emitter', MagicMock())
    try:
        result = await sessions.start_linkedin_update('offline-session', sessions.LinkedInUpdateRequest(updates=[{'section':'headline','content':'Engineer'}]), None)
        assert result['status'] == 'ok' and len(tasks) == 1
    finally:
        for task in tasks: task.close()


def test_gateway_imports_with_optional_packages_completely_unavailable():
    import subprocess
    import sys
    from pathlib import Path
    script = '''
import importlib.abc, sys
class Unavailable(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'browser_use','evoagentx','litellm'}:
            raise ModuleNotFoundError('optional engine absent')
sys.meta_path.insert(0, Unavailable())
import backend.gateway.main
import backend.browser.tools.browser_use_applier
import backend.browser.tools.browser_use_discovery
import backend.browser.tools.linkedin_updater
import backend.optimization.evolve
'''
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
