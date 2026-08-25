"""Enrollment challenge/attestation API for agent lineage."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.db import get_session
from agora_api.passports_service import attest_enrollment, create_enrollment_challenge
from agora_api.ratelimit import enforce_rate_limit

router = APIRouter(prefix="/v1/enrollment", tags=["enrollment"])


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/challenge", status_code=201)
async def challenge(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    await enforce_rate_limit("enrollment_challenge", _client_key(request))
    return await create_enrollment_challenge(session, await request.json())


@router.post("/attest")
async def attest(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    await enforce_rate_limit("enrollment_attest", _client_key(request))
    return await attest_enrollment(
        session,
        await request.json(),
        getattr(request.state, "trace_id", None),
    )
