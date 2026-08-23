"""Device lifecycle (S1.1-T01/T02 redesign).

Authorization model:
- `POST /ping` — authenticated no-op via the shared CurrentDevice dependency.
- `POST /revoke-signed` — canonical self-revocation: proof of possession of
  the device private key (works even after session expiry; the kill switch
  never depends on session freshness). Idempotent.
- `POST /{device_id}/revoke` — session-authenticated. A device may revoke
  ITSELF only; acting on any other device returns a structured 403
  `owner_authority_required`. Owner-level revocation is explicitly deferred
  to Sprint 02 human accounts (ADR-0009) — no fake ownership mechanism here.

Knowing a public device_id is never sufficient to revoke it (SEC).
`device.revoked` is appended exactly once, on the authorized→revoked
transition, by the single shared `_revoke()` service function.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.boundary import validate_boundary
from agora_api.crypto import verify_signature
from agora_api.db import get_session
from agora_api.errors import NotFound, OwnerAuthorityRequired, SignatureInvalid
from agora_api.events import append_event, now_utc
from agora_api.logging import get_logger
from agora_api.models import Device

router = APIRouter(prefix="/v1/devices", tags=["devices"])
log = get_logger("agora.api.devices")

REVOKE_CONTEXT = "agora.revoke.v1"
REVOKE_TIMESTAMP_WINDOW = timedelta(seconds=300)


async def _revoke(session: AsyncSession, device: Device, trace_id: str | None) -> dict:
    """Single transition point. Emits device.revoked exactly once."""
    if device.status == "revoked":
        return {"device_id": device.device_id, "status": "revoked", "already_revoked": True}
    device.status = "revoked"
    device.revoked_at = now_utc()
    await append_event(
        session,
        event_type="device.revoked",
        actor={"agent_id": device.agent_id, "device_id": device.device_id},
        payload={"device_id": device.device_id, "agent_id": device.agent_id},
        trace_id=trace_id,
    )
    await session.commit()
    log.info("device.revoked", device_id=device.device_id, agent_id=device.agent_id)
    # Terminate any live realtime connection for this device (S2-T08).
    import contextlib

    from agora_api.realtime import gateway

    with contextlib.suppress(Exception):  # revocation must not depend on NATS health
        await gateway.publish("system", "device_revoked", {"device_id": device.device_id})
    return {"device_id": device.device_id, "status": "revoked", "already_revoked": False}


@router.post("/ping")
async def device_ping(
    device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    """Authenticated no-op. Presence is ephemeral — never written to the ledger."""
    device.last_seen_at = now_utc()
    await session.commit()
    return {"device_id": device.device_id, "agent_id": device.agent_id, "status": device.status}


@router.post("/revoke-signed")
async def revoke_signed(
    request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    body = await request.json()
    validate_boundary("devices.schema.json", "/$defs/RevokeSignedRequest", body)

    device = await session.get(Device, body["device_id"])
    if device is None:
        raise NotFound("Device not found.")

    try:
        ts = datetime.fromisoformat(body["timestamp"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise SignatureInvalid("Invalid timestamp.") from exc
    if abs(datetime.now(UTC) - ts) > REVOKE_TIMESTAMP_WINDOW:
        raise SignatureInvalid("Revocation timestamp outside acceptance window.")

    message = f"{REVOKE_CONTEXT}|{body['device_id']}|{body['timestamp']}".encode()
    if not verify_signature(device.public_key, message, body["signature"]):
        raise SignatureInvalid("Revocation signature verification failed.")

    return await _revoke(session, device, getattr(request.state, "trace_id", None))


@router.post("/{device_id}/revoke")
async def revoke_device(
    device_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    if device.device_id != device_id:
        raise OwnerAuthorityRequired(
            "A device may only revoke itself. Owner-level revocation arrives "
            "with human accounts in Sprint 02 (ADR-0009)."
        )
    return await _revoke(session, device, getattr(request.state, "trace_id", None))
