"""Public read surface for the human web shell and lineage operator view."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.agent_identity import agent_identity_credential
from agora_api.authz import CurrentDevice
from agora_api.boundary import validate_boundary
from agora_api.db import get_session
from agora_api.errors import NotFound, OwnerAuthorityRequired
from agora_api.models import Agent, Device, Event
from agora_api.passports_service import authorize_device, lineage, rotate_agent_key
from agora_api.routes.devices import _revoke

router = APIRouter(prefix="/v1/agents", tags=["agents"])


def _agent_dict(agent: Agent, devices: list[Device]) -> dict:
    return {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "status": agent.status,
        "current_version_id": agent.current_version_id,
        "created_at": agent.created_at.isoformat(),
        "devices": [
            {
                "device_id": d.device_id,
                "label": d.label,
                "status": d.status,
                "created_at": d.created_at.isoformat(),
                "revoked_at": d.revoked_at.isoformat() if d.revoked_at else None,
            }
            for d in devices
        ],
    }


@router.get("")
async def list_agents(session: AsyncSession = Depends(get_session)) -> dict:
    agents = (await session.execute(select(Agent).order_by(Agent.agent_id))).scalars().all()
    devices = (await session.execute(select(Device))).scalars().all()
    by_agent: dict[str, list[Device]] = {}
    for d in devices:
        by_agent.setdefault(d.agent_id, []).append(d)
    return {"agents": [_agent_dict(a, by_agent.get(a.agent_id, [])) for a in agents]}


@router.get("/{agent_id}")
async def get_agent(agent_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise NotFound("Agent not found.")
    devices = (
        (await session.execute(select(Device).where(Device.agent_id == agent_id)))
        .scalars()
        .all()
    )
    last_event = (
        await session.execute(
            select(Event)
            .where(Event.actor["agent_id"].astext == agent_id)
            .order_by(desc(Event.event_id))
            .limit(1)
        )
    ).scalar_one_or_none()
    from agora_api.presence import current_space

    data = _agent_dict(agent, list(devices))
    data["current_space_id"] = await current_space(agent_id)
    data["last_public_activity"] = (
        {
            "event_id": last_event.event_id,
            "event_type": last_event.event_type,
            "occurred_at": last_event.occurred_at.isoformat(),
        }
        if last_event
        else None
    )
    return data


@router.get("/{agent_id}/events")
async def list_agent_events(agent_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    events = (
        (
            await session.execute(
                select(Event)
                .where(Event.actor["agent_id"].astext == agent_id)
                .order_by(desc(Event.event_id))
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    return {
        "events": [
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "occurred_at": e.occurred_at.isoformat(),
                "payload": e.payload,
            }
            for e in events
        ]
    }


@router.get("/{agent_id}/lineage")
async def get_lineage(agent_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    return await lineage(session, agent_id)


@router.get("/{agent_id}/identity-credential")
async def get_identity_credential(
    agent_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    """Return the signed public AgentGenesis credential and optional SBT mirror metadata."""
    return await agent_identity_credential(session, agent_id)


@router.post("/{agent_id}/devices/authorize")
async def post_authorize_device(
    agent_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_boundary("passports.schema.json", "/$defs/AuthorizeDeviceRequest", body)
    target_device_id = body["device_id"]
    assurance_level = body.get("assurance_level", "device")
    if not isinstance(target_device_id, str):
        from agora_api.errors import ValidationFailed

        raise ValidationFailed("device_id is required.")
    return await authorize_device(
        session,
        agent_id=agent_id,
        target_device_id=target_device_id,
        current_device=device,
        assurance_level=assurance_level,
        trace_id=getattr(request.state, "trace_id", None),
    )


@router.post("/{agent_id}/devices/{device_id}/revoke")
async def post_revoke_agent_device(
    agent_id: str,
    device_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    if device.agent_id != agent_id or device.device_id != device_id:
        raise OwnerAuthorityRequired(
            "Only authenticated self-revocation is available without owner authority."
        )
    return await _revoke(session, device, getattr(request.state, "trace_id", None))


@router.post("/{agent_id}/keys/rotate")
async def post_rotate_key(
    agent_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await rotate_agent_key(
        session,
        agent_id=agent_id,
        current_device=device,
        payload=await request.json(),
        trace_id=getattr(request.state, "trace_id", None),
    )
