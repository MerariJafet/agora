"""Rate limiter behavior against real Redis."""

import secrets

import pytest

from agora_api import ratelimit
from agora_api.config import Settings
from agora_api.errors import RateLimited

pytestmark = pytest.mark.integration


async def test_rate_limit_enforced(monkeypatch):
    limited = Settings(ratelimit_max_requests=3, ratelimit_window_seconds=60)
    monkeypatch.setattr(ratelimit, "get_settings", lambda: limited)
    client = f"client-{secrets.token_hex(4)}"
    for _ in range(3):
        await ratelimit.enforce_rate_limit("test_bucket", client)
    with pytest.raises(RateLimited):
        await ratelimit.enforce_rate_limit("test_bucket", client)


async def test_rate_limit_isolated_per_client(monkeypatch):
    limited = Settings(ratelimit_max_requests=1, ratelimit_window_seconds=60)
    monkeypatch.setattr(ratelimit, "get_settings", lambda: limited)
    await ratelimit.enforce_rate_limit("iso_bucket", f"a-{secrets.token_hex(4)}")
    await ratelimit.enforce_rate_limit("iso_bucket", f"b-{secrets.token_hex(4)}")  # no raise
