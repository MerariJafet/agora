from fastapi import APIRouter
from sqlalchemy import text

from agora_api import __version__
from agora_api.db import session_factory
from agora_api.ratelimit import get_redis

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
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
    healthy = all(v == "ok" for v in checks.values())
    return {"status": "ok" if healthy else "degraded", "version": __version__, "checks": checks}
