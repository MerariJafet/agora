from unittest.mock import AsyncMock, MagicMock

import pytest
from agora_api.routes import health
from fastapi import Response


@pytest.mark.parametrize('postgres_ok,redis_ok,expected', [
    (True, True, 200), (False, True, 503), (True, False, 503), (False, False, 503),
])
async def test_dependency_failure_is_not_a_successful_probe(
    monkeypatch, postgres_ok, redis_ok, expected
):
    session = AsyncMock()
    if not postgres_ok:
        session.execute.side_effect = RuntimeError('private connection details')
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(health, 'session_factory', lambda: lambda: context)
    redis = AsyncMock()
    if not redis_ok:
        redis.ping.side_effect = RuntimeError('private redis details')
    monkeypatch.setattr(health, 'get_redis', lambda: redis)
    monkeypatch.setattr(health, 'outbox_stats', AsyncMock(return_value={}))
    response = Response()
    body = await health.healthz(response)
    assert response.status_code == expected
    assert body['status'] == ('ok' if expected == 200 else 'degraded')
    assert 'private' not in str(body)
