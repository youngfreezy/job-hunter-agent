# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Tests for Paperclip integration — heartbeat reporting decorator."""

import asyncio
from unittest.mock import patch, MagicMock

import pytest

from backend.shared.paperclip_integration import with_paperclip_reporting, init_paperclip


@pytest.fixture(autouse=True)
def reset_paperclip():
    """Reset Paperclip initialization state between tests."""
    import backend.shared.paperclip_integration as mod
    mod._initialized = False
    yield
    mod._initialized = False


class TestWithPaperclipReporting:
    """Test the heartbeat reporting decorator."""

    @pytest.mark.asyncio
    async def test_decorator_noop_when_disabled(self):
        """When PAPERCLIP_ENABLED=false, decorator runs original function unchanged."""
        call_count = 0

        async def my_task():
            nonlocal call_count
            call_count += 1
            return 42

        wrapped = with_paperclip_reporting("test-agent")(my_task)
        result = await wrapped()
        assert result == 42
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_decorator_reports_on_success(self):
        """When Paperclip is initialized, decorator reports heartbeat on success."""
        import backend.shared.paperclip_integration as mod
        mod._initialized = True

        async def my_task():
            return "done"

        with patch("backend.shared.paperclip_integration.get_settings") as mock_settings, \
             patch("backend.shared.paperclip_client.report_heartbeat") as mock_report:
            mock_settings.return_value.PAPERCLIP_ENABLED = True
            wrapped = with_paperclip_reporting("test-agent")(my_task)
            result = await wrapped()

            assert result == "done"
            mock_report.assert_called_once()
            call_args = mock_report.call_args
            assert call_args.kwargs["agent_name"] == "test-agent"
            assert call_args.kwargs["status"] == "completed"
            assert call_args.kwargs["error"] is None

    @pytest.mark.asyncio
    async def test_decorator_reports_on_failure(self):
        """When Paperclip is initialized, decorator reports heartbeat on failure."""
        import backend.shared.paperclip_integration as mod
        mod._initialized = True

        async def my_task():
            raise ValueError("something broke")

        with patch("backend.shared.paperclip_integration.get_settings") as mock_settings, \
             patch("backend.shared.paperclip_client.report_heartbeat") as mock_report:
            mock_settings.return_value.PAPERCLIP_ENABLED = True
            wrapped = with_paperclip_reporting("test-agent")(my_task)

            with pytest.raises(ValueError, match="something broke"):
                await wrapped()

            mock_report.assert_called_once()
            call_args = mock_report.call_args
            assert call_args.kwargs["status"] == "failed"
            assert "something broke" in call_args.kwargs["error"]

    @pytest.mark.asyncio
    async def test_decorator_swallows_reporting_errors(self):
        """If Paperclip reporting itself fails, the original function's result is preserved."""
        import backend.shared.paperclip_integration as mod
        mod._initialized = True

        async def my_task():
            return "success"

        with patch("backend.shared.paperclip_integration.get_settings") as mock_settings, \
             patch("backend.shared.paperclip_client.report_heartbeat", side_effect=Exception("paperclip down")):
            mock_settings.return_value.PAPERCLIP_ENABLED = True
            wrapped = with_paperclip_reporting("test-agent")(my_task)
            result = await wrapped()
            assert result == "success"  # Original result preserved despite reporting failure


class TestInitPaperclip:
    """Test Paperclip initialization."""

    def test_init_returns_false_when_disabled(self):
        """init_paperclip() returns False when PAPERCLIP_ENABLED=false."""
        with patch("backend.shared.paperclip_integration.get_settings") as mock_settings:
            mock_settings.return_value.PAPERCLIP_ENABLED = False
            assert init_paperclip() is False

    def test_init_returns_false_when_no_credentials(self):
        """init_paperclip() returns False when no agent env vars are set."""
        with patch("backend.shared.paperclip_integration.get_settings") as mock_settings, \
             patch("dotenv.load_dotenv"), \
             patch.dict("os.environ", {}, clear=True):
            mock_settings.return_value.PAPERCLIP_ENABLED = True
            import backend.shared.paperclip_integration as mod
            mod._initialized = False
            result = init_paperclip()
            assert result is False

    def test_init_configures_agents_from_env(self):
        """init_paperclip() reads agent credentials from env vars."""
        env = {
            "PAPERCLIP_AGENT_MOLTBOOK": "agent-id-1:token-1",
            "PAPERCLIP_AGENT_AUTOPILOT": "agent-id-2:token-2",
        }
        with patch("backend.shared.paperclip_integration.get_settings") as mock_settings, \
             patch.dict("os.environ", env, clear=False), \
             patch("backend.shared.paperclip_client.configure_agents") as mock_configure:
            mock_settings.return_value.PAPERCLIP_ENABLED = True
            result = init_paperclip()

            assert result is True
            mock_configure.assert_called_once()
            agents = mock_configure.call_args[0][0]
            assert "moltbook" in agents
            assert agents["moltbook"]["id"] == "agent-id-1"
            assert agents["moltbook"]["token"] == "token-1"
            assert "autopilot" in agents
