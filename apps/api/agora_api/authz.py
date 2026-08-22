"""Reusable device authorization (S1.1-T02).

Single enforcement point for "who is this device and is it still trusted".
Every authenticated surface — HTTP today, WebSocket/A2A tomorrow — resolves
credentials through `resolve_device_session()` (transport-agnostic, takes the
raw bearer token) or the FastAPI dependency `CurrentDevice`.

Guarantees:
- Revoked devices are rejected with 403 `device_revoked` everywhere.
- There is exactly one code path deciding this; no ad-hoc checks in routes.
- Session issuance also refuses revoked devices, so no refresh/replay path
  can revive one (SEC: "revocation cannot be undone by refresh").
"""

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.auth import auth_provider
from agora_api.db import get_session
from agora_api.errors import AuthRequired
from agora_api.models import Device


def bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthRequired("Missing bearer token.")
    return authorization.removeprefix("Bearer ")


async def resolve_device_session(session: AsyncSession, token: str) -> Device:
    """Transport-agnostic: validate session material and revocation state.
    WebSocket / A2A handshakes must call this same function."""
    return await auth_provider.authenticate_device(session, token)


async def current_device(
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> Device:
    return await resolve_device_session(session, bearer_token(authorization))


CurrentDevice = Annotated[Device, Depends(current_device)]
