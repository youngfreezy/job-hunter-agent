"""Connection observability must not log credential-bearing Redis URLs."""
from unittest.mock import AsyncMock, MagicMock
import pytest
from backend.shared import redis_client as module


@pytest.mark.asyncio
async def test_connect_logs_no_password_or_full_connection_url(monkeypatch):
    pool=MagicMock(disconnect=AsyncMock())
    monkeypatch.setattr(module.aioredis.ConnectionPool, 'from_url', lambda *a, **kw:pool)
    monkeypatch.setattr(module.aioredis, 'Redis', lambda **kw:MagicMock(aclose=AsyncMock()))
    client=module.RedisClient('redis://user:fixture-private-password@localhost:6379/0')
    logger=MagicMock(); monkeypatch.setattr(module, 'logger', logger)
    await client.connect()
    rendered=' '.join(call.args[0] % call.args[1:] if len(call.args)>1 else call.args[0]
                      for call in logger.info.call_args_list)
    assert 'Redis connected' in rendered
    assert 'fixture-private-password' not in rendered
    assert 'redis://' not in rendered
    await client.close()
