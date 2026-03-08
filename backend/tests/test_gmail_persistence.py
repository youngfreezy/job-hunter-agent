"""Tests for Gmail token persistence via Redis."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_redis():
    """Mock RedisClient with async JSON helpers."""
    client = AsyncMock()
    client.set_json = AsyncMock()
    client.get_json = AsyncMock(return_value=None)
    client.delete = AsyncMock()
    return client


class TestStoreGmailToken:
    """store_gmail_token should persist token data to Redis."""

    def test_stores_token_to_redis(self, mock_redis):
        with patch("backend.shared.gmail_client.redis_client", mock_redis):
            from backend.shared.gmail_client import store_gmail_token

            asyncio.get_event_loop().run_until_complete(
                store_gmail_token(
                    session_id="sess-123",
                    access_token="at_abc",
                    refresh_token="rt_xyz",
                    client_id="cid",
                    client_secret="csec",
                )
            )

            mock_redis.set_json.assert_called_once()
            call_args = mock_redis.set_json.call_args
            key = call_args[0][0]
            data = call_args[0][1]
            assert key == "gmail_token:sess-123"
            assert data["access_token"] == "at_abc"
            assert data["refresh_token"] == "rt_xyz"
            assert data["client_id"] == "cid"
            assert data["client_secret"] == "csec"

    def test_stores_without_refresh_token(self, mock_redis):
        with patch("backend.shared.gmail_client.redis_client", mock_redis):
            from backend.shared.gmail_client import store_gmail_token

            asyncio.get_event_loop().run_until_complete(
                store_gmail_token(
                    session_id="sess-456",
                    access_token="at_only",
                )
            )

            call_args = mock_redis.set_json.call_args
            data = call_args[0][1]
            assert data["access_token"] == "at_only"
            assert data["refresh_token"] is None


class TestGetService:
    """_get_service should reconstruct credentials from Redis."""

    def test_returns_none_when_no_token(self, mock_redis):
        mock_redis.get_json = AsyncMock(return_value=None)
        with patch("backend.shared.gmail_client.redis_client", mock_redis):
            from backend.shared.gmail_client import _get_service

            result = asyncio.get_event_loop().run_until_complete(
                _get_service("no-such-session")
            )
            assert result is None

    def test_reconstructs_credentials_from_redis(self, mock_redis):
        mock_redis.get_json = AsyncMock(return_value={
            "access_token": "at_test",
            "refresh_token": "rt_test",
            "client_id": "cid_test",
            "client_secret": "csec_test",
        })
        with (
            patch("backend.shared.gmail_client.redis_client", mock_redis),
            patch("backend.shared.gmail_client._build_gmail_service") as mock_build,
        ):
            mock_build.return_value = MagicMock()
            from backend.shared.gmail_client import _get_service

            result = asyncio.get_event_loop().run_until_complete(
                _get_service("sess-789")
            )

            mock_redis.get_json.assert_called_with("gmail_token:sess-789")
            mock_build.assert_called_once()
            creds = mock_build.call_args[0][0]
            assert creds.token == "at_test"
            assert result is not None


class TestClearGmailToken:
    """clear_gmail_token should remove the Redis key."""

    def test_deletes_redis_key(self, mock_redis):
        with patch("backend.shared.gmail_client.redis_client", mock_redis):
            from backend.shared.gmail_client import clear_gmail_token

            asyncio.get_event_loop().run_until_complete(
                clear_gmail_token("sess-del")
            )

            mock_redis.delete.assert_called_once_with("gmail_token:sess-del")
