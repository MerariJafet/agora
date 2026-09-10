from fastapi import APIRouter, Response
from sqlalchemy import text

from agora_api import __version__
from agora_api.db import session_factory
from agora_api.publisher import outbox_stats
from agora_api.ratelimit import get_redis

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz(response: Response) -> dict:
    checks: dict[str, str] = {}
    try:
        async with session_factory()() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception:
        checks["postgres"] = "unavailable"
    try:
        await get_redis().ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "unavailable"
    outbox: dict | None = None
    try:
        async with session_factory()() as session:
            outbox = await outbox_stats(session)
    except Exception:
        outbox = None
    healthy = all(v == "ok" for v in checks.values())
    response.status_code = 200 if healthy else 503
    return {
        "status": "ok" if healthy else "degraded",
        "version": __version__,
        "checks": checks,
        "outbox": outbox,
    }
