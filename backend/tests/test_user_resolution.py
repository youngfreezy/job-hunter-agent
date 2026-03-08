"""Tests for user resolution from JWT-validated request state."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


class TestGetCurrentUser:
    """get_current_user should extract email from request.state and resolve user."""

    def _make_request(self, email: str | None = None) -> MagicMock:
        req = MagicMock()
        req.state.user_email = email
        return req

    def test_valid_email_returns_user(self):
        from backend.gateway.deps import get_current_user

        with patch("backend.gateway.deps.get_or_create_user") as mock:
            mock.return_value = {
                "id": "uuid-123",
                "email": "alice@example.com",
                "wallet_balance": 0.0,
                "free_applications_remaining": 3,
            }
            user = get_current_user(self._make_request("alice@example.com"))
            assert user["id"] == "uuid-123"
            assert user["email"] == "alice@example.com"
            mock.assert_called_once_with("alice@example.com")

    def test_missing_header_raises_401(self):
        from backend.gateway.deps import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            get_current_user(self._make_request())
        assert exc_info.value.status_code == 401

    def test_idempotent_same_email(self):
        from backend.gateway.deps import get_current_user

        user_data = {
            "id": "uuid-456",
            "email": "bob@example.com",
            "wallet_balance": 10.0,
            "free_applications_remaining": 2,
        }
        with patch("backend.gateway.deps.get_or_create_user", return_value=user_data):
            u1 = get_current_user(self._make_request("bob@example.com"))
            u2 = get_current_user(self._make_request("bob@example.com"))
            assert u1["id"] == u2["id"]
