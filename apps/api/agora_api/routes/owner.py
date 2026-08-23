"""Authenticated owner surface: my agents, secure claim issuance, and
owner-level device revocation (S2-T04/T05). All state-changing routes require
CSRF (MutatingOwner)."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.db import get_session
from agora_api.errors import Conflict, NotFound, OwnerAuthorityRequired, ValidationFailed
from agora_api.ids import is_valid
from agora_api.models import Agent, Device
from agora_api.owners import CurrentOwner, MutatingOwner, create_claim
from agora_api.ratelimit import enforce_rate_limit
from agora_api.routes.devices import _revoke

router = APIRouter(prefix="/v1/owner", tags=["owner"])


@router.get("/agents")
async def my_agents(
    owner: CurrentOwner, session: AsyncSession = Depends(get_session)
) -> dict:
    agents = (
        (await session.execute(select(Agent).where(Agent.owner_id == owner.user_id)))
        .scalars()
        .all()
    )
    agent_ids = [a.agent_id for a in agents]
    devices = (
        (await session.execute(select(Device).where(Device.agent_id.in_(agent_ids))))
        .scalars()
        .all()
        if agent_ids
        else []
    )
    by_agent: dict[str, list] = {}
    for d in devices:
        by_agent.setdefault(d.agent_id, []).append(
            {"device_id": d.device_id, "label": d.label, "status": d.status}
        )
    return {
        "agents": [
            {
                "agent_id": a.agent_id,
                "name": a.name,
                "status": a.status,
                "devices": by_agent.get(a.agent_id, []),
            }
            for a in agents
        ]
    }


@router.post("/claims", status_code=201)
async def request_claim(
    request: Request, owner: MutatingOwner, session: AsyncSession = Depends(get_session)
) -> dict:
    """Issue a one-time pairing code for an UNOWNED agent. The code must then
    be proven by the agent's device (`agora claim <code>`) — knowing an
    agent_id is never sufficient (SEC-005)."""
    await enforce_rate_limit("owner_claim", owner.user_id)
    body = await request.json()
    agent_id = body.get("agent_id") if isinstance(body, dict) else None
    if not isinstance(agent_id, str) or not is_valid(agent_id, "agt"):
        raise ValidationFailed("agent_id required.")
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise NotFound("Agent not found.")
    if agent.owner_id is not None:
        # Ownership never changes implicitly — future governance only (ADR-0011).
        raise Conflict("Agent is already owned.")
    code = await create_claim(session, owner, agent_id)
    await session.commit()
    return {
        "agent_id": agent_id,
        "claim_code": code,  # shown once; only its hash is stored
        "expires_in_seconds": 600,
        "next_step": "Run `agora claim <code>` on the machine that holds the agent's key.",
    }


@router.post("/devices/{device_id}/revoke")
async def owner_revoke_device(
    device_id: str,
    request: Request,
    owner: MutatingOwner,
    session: AsyncSession = Depends(get_session),
) -> dict:
    device = await session.get(Device, device_id)
    if device is None:
        raise NotFound("Device not found.")
    agent = await session.get(Agent, device.agent_id)
    if agent is None or agent.owner_id != owner.user_id:
        raise OwnerAuthorityRequired("This device does not belong to one of your agents.")
    return await _revoke(session, device, getattr(request.state, "trace_id", None))
