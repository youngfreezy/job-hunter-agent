"""Reject invalid pagination at the HTTP boundary before it reaches SQL."""

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.gateway.routes import developer, marketplace


@pytest.mark.parametrize("path", ["/api/marketplace/agents/demo/reviews?limit=-1",
                                  "/api/marketplace/agents/demo/reviews?offset=-1",
                                  "/api/developer/webhooks/demo/deliveries?limit=-1"])
def test_invalid_page_bounds_do_not_reach_storage(monkeypatch, path):
    read = MagicMock(side_effect=AssertionError("invalid SQL bounds reached storage"))
    monkeypatch.setattr(marketplace, "list_reviews", read)
    monkeypatch.setattr(developer, "list_deliveries", read)
    monkeypatch.setattr(developer, "get_current_user", lambda _: {"id": "owner"})
    app = FastAPI()
    app.include_router(marketplace.router)
    app.include_router(developer.router)
    assert TestClient(app).get(path).status_code == 422
    read.assert_not_called()
