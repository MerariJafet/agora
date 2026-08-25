"""Short-lived cryptographic PassportSession API."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.db import get_session
from agora_api.passports_service import issue_passport, verify_passport
from agora_api.ratelimit import enforce_rate_limit

router = APIRouter(prefix="/v1/passports", tags=["passports"])


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/issue", status_code=201)
async def issue(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    await enforce_rate_limit("passport_issue", _client_key(request))
    return await issue_passport(
        session,
        await request.json(),
        getattr(request.state, "trace_id", None),
    )


@router.post("/verify")
async def verify(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    body = await request.json()
    token = body.get("passport_token") if isinstance(body, dict) else None
    if not isinstance(token, str):
        from agora_api.errors import AuthRequired

        raise AuthRequired("passport_token is required.")
    row = await verify_passport(session, token)
    return {
        "passport_id": row.passport_id,
        "agent_id": row.agent_id,
        "device_id": row.device_id,
        "active": True,
        "expires_at": row.expires_at.isoformat(),
    }
