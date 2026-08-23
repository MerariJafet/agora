"""Owner authentication routes (development provider only in Sprint 02)."""

import contextlib

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.config import get_settings
from agora_api.db import get_session
from agora_api.errors import ValidationFailed
from agora_api.owners import (
    SESSION_COOKIE,
    CurrentOwner,
    create_web_session,
    get_owner_auth_provider,
    resolve_web_session,
)
from agora_api.ratelimit import enforce_rate_limit

router = APIRouter(prefix="/v1/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=get_settings().is_production,
        max_age=24 * 3600,
        path="/",
    )


@router.post("/dev/login")
async def dev_login(
    request: Request, response: Response, session: AsyncSession = Depends(get_session)
) -> dict:
    """Development login: username only. Fails closed in production
    (get_owner_auth_provider raises 403 before any credential is read)."""
    await enforce_rate_limit("auth_login", request.client.host if request.client else "unknown")
    provider = get_owner_auth_provider()
    body = await request.json()
    if not isinstance(body, dict):
        raise ValidationFailed("Expected JSON object.")
    user = await provider.login(session, body)
    token, csrf, expires_at = await create_web_session(session, user)
    await session.commit()
    _set_session_cookie(response, token)
    return {
        "user_id": user.user_id,
        "username": user.username,
        "csrf_token": csrf,
        "expires_at": expires_at,
    }


@router.get("/me")
async def me(
    request: Request,
    owner: CurrentOwner,
    session: AsyncSession = Depends(get_session),
) -> dict:
    ws = await resolve_web_session(session, request.cookies.get(SESSION_COOKIE))
    return {"user_id": owner.user_id, "username": owner.username, "csrf_token": ws.csrf_token}


@router.post("/logout")
async def logout(
    request: Request, response: Response, session: AsyncSession = Depends(get_session)
) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        with contextlib.suppress(Exception):  # logout is best-effort
            ws = await resolve_web_session(session, token)
            await session.delete(ws)
            await session.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"logged_out": True}
