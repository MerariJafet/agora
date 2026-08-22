"""Rate limiting for registration-sensitive endpoints.

Fixed-window counters in Redis. Behavior when Redis is unavailable:
- development: fail open with a warning (local DX),
- production: fail closed on sensitive endpoints (SEC posture: an attacker
  must not be able to disable rate limiting by degrading Redis).
"""

import redis.asyncio as aioredis

from agora_api.config import get_settings
from agora_api.errors import RateLimited
from agora_api.logging import get_logger

log = get_logger("agora.api.ratelimit")

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def enforce_rate_limit(bucket: str, client_key: str) -> None:
    settings = get_settings()
    window = settings.ratelimit_window_seconds
    key = f"rl:{bucket}:{client_key}"
    try:
        r = get_redis()
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, window)
        if count > settings.ratelimit_max_requests:
            raise RateLimited("Too many requests. Retry later.")
    except RateLimited:
        raise
    except Exception as exc:  # Redis unavailable
        if settings.is_production:
            log.error("ratelimit.redis_unavailable_fail_closed", bucket=bucket, error=str(exc))
            raise RateLimited("Rate limiter unavailable.") from exc
        log.warning("ratelimit.redis_unavailable_fail_open_dev", bucket=bucket)
