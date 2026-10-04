"""Global selector maintenance is an owner operation, not a public browser trigger."""
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.gateway.routes import selectors


@pytest.mark.parametrize('endpoint,method', [('/api/selectors/status','get'),('/api/selectors/health-check','post')])
@pytest.mark.parametrize('identity', [None, {'id':'visitor'}])
def test_selector_maintenance_rejects_nonowner_before_store_or_browser(monkeypatch,endpoint,method,identity):
    app=FastAPI()
    app.include_router(selectors.router)
    def user(_request):
        if identity is None:
            from fastapi import HTTPException
            raise HTTPException(401,'Sign in required')
        return identity
    monkeypatch.setattr(selectors,'get_current_user',user,raising=False)
    monkeypatch.setattr(selectors,'is_server_model_owner',lambda uid:uid=='owner',raising=False)
    def forbidden(*args,**kwargs): raise AssertionError('Global store must not be accessed')
    monkeypatch.setattr(selectors,'get_all_selectors',forbidden,raising=False)
    monkeypatch.setattr(selectors,'get_all_discovery_selectors',forbidden)
    monkeypatch.setattr(selectors,'get_all_apply_selectors',forbidden)
    runner=AsyncMock(side_effect=AssertionError('Browser must not start'))
    monkeypatch.setattr('backend.shared.selector_health.run_selector_health_check',runner)
    response=getattr(TestClient(app),method)(endpoint)
    assert response.status_code==(401 if identity is None else 403)
    runner.assert_not_awaited()


def test_selector_owner_can_run_maintenance(monkeypatch):
    app=FastAPI();app.include_router(selectors.router)
    monkeypatch.setattr(selectors,'get_current_user',lambda _: {'id':'owner'},raising=False)
    monkeypatch.setattr(selectors,'is_server_model_owner',lambda uid:uid=='owner',raising=False)
    runner=AsyncMock(return_value={'discovery':{},'apply':{}})
    monkeypatch.setattr('backend.shared.selector_health.run_selector_health_check',runner)
    response=TestClient(app).post('/api/selectors/health-check?platform=indeed')
    assert response.status_code==200
    runner.assert_awaited_once_with(platform='indeed')
