"""Public read surface for the human web shell. Single-query list endpoints
(no N+1): devices are aggregated in one round trip."""

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.db import get_session
from agora_api.errors import NotFound
from agora_api.models import Agent, Device, Event

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
