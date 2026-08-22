"""Device lifecycle: authenticated ping (proves session works) and revocation.

Revocation model (S1-T06): the human owner (web shell, local trust boundary in
Sprint 01) or the device itself can revoke. After revocation every
authenticated call fails with 403 device_revoked (SEC-003).
"""

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.auth import auth_provider
from agora_api.db import get_session
from agora_api.errors import AuthRequired, NotFound
from agora_api.events import append_event, now_utc
from agora_api.models import Device

router = APIRouter(prefix="/v1/devices", tags=["devices"])


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthRequired("Missing bearer token.")
    return authorization.removeprefix("Bearer ")


@router.post("/ping")
async def device_ping(
    session: AsyncSession = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> dict:
    """Authenticated no-op used by `agora status` and revocation tests.
    Presence is ephemeral — deliberately NOT written to the event ledger."""
    device = await auth_provider.authenticate_device(session, _bearer(authorization))
    device.last_seen_at = now_utc()
    await session.commit()
    return {"device_id": device.device_id, "agent_id": device.agent_id, "status": device.status}


@router.post("/{device_id}/revoke")
async def revoke_device(
    device_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    device = await session.get(Device, device_id)
    if device is None:
        raise NotFound("Device not found.")
    if device.status == "revoked":
        return {"device_id": device.device_id, "status": "revoked"}  # idempotent

    device.status = "revoked"
    device.revoked_at = now_utc()
    await append_event(
        session,
        event_type="device.revoked",
        actor={"agent_id": device.agent_id, "device_id": device.device_id},
        payload={"device_id": device.device_id, "agent_id": device.agent_id},
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return {"device_id": device.device_id, "status": "revoked"}
