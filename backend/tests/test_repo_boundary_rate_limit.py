"""Rate limiting trusts ASGI identity and fails closed for sensitive operations."""

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from starlette.requests import Request

from backend.gateway.middleware.rate_limit import RateLimitMiddleware, _get_identifier


def test_forwarded_header_cannot_choose_unauthenticated_rate_limit_bucket():
    request = Request({"type": "http", "client": ("203.0.113.10", 1000),
                       "headers": [(b"x-forwarded-for", b"attacker-chosen-bucket")]})
    assert _get_identifier(request) == "ip:203.0.113.10"


def test_authenticated_bucket_keeps_verified_user_identity():
    request = Request({"type": "http", "client": ("203.0.113.10", 1000), "headers": []})
    request.state.user_email = "owner@example.com"
    assert _get_identifier(request) == "user:owner@example.com"


@pytest.mark.asyncio
async def test_account_erasure_removes_exact_email_based_buckets(monkeypatch):
    from types import SimpleNamespace
    from backend.gateway.middleware import rate_limit
    delete = AsyncMock(return_value=2)
    monkeypatch.setattr(rate_limit.redis_client, "_redis", SimpleNamespace(delete=delete))
    assert await rate_limit.clear_user_rate_limits("star*owner@example.com") == 2
    keys = delete.call_args.args
    assert keys and all(key.startswith("ratelimit:user:star*owner@example.com:") for key in keys)
    assert "ratelimit:user:star*owner@example.com:api_general" in keys


@pytest.mark.parametrize("path", ["/api/auth/login", "/api/auth/register", "/api/sessions",
                                  "/api/sessions/example/test-apply", "/api/sms/verify",
                                  "/api/sms/confirm", "/api/browserbase/login-sessions"])
def test_sensitive_requests_stop_when_rate_limit_storage_fails(monkeypatch, path):
    guard = AsyncMock(side_effect=RuntimeError("redis unavailable"))
    monkeypatch.setattr(RateLimitMiddleware, "_check_rate_limit", guard)
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)
    app.add_api_route(path, lambda: {"called": True}, methods=["POST"])
    response = TestClient(app).post(path)
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    assert response.json() == {"detail": "Request protection is temporarily unavailable. Please try again shortly."}


@pytest.mark.parametrize("path,method", [("/api/marketplace/agents", "GET"),
                                        ("/api/sms/webhook", "POST"), ("/api/stripe/webhook", "POST")])
def test_other_routes_remain_available_when_rate_limit_storage_fails(monkeypatch, path, method):
    monkeypatch.setattr(RateLimitMiddleware, "_check_rate_limit", AsyncMock(side_effect=RuntimeError("redis unavailable")))
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)
    app.add_api_route(path, lambda: {"called": True}, methods=[method])
    assert TestClient(app).request(method, path).status_code == 200
