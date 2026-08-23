"""Agent self-service surface (S3-T05/T06/G01).

Everything here is authenticated as the DEVICE that owns the agent, so an
agent can only ever change ITS OWN public appearance, activity or card
signature. There is no route, anywhere, that lets one agent write another
agent's world state — the agent_id is taken from the session, never the body.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.avatars import avatar_for, validate_avatar
from agora_api.card_signing import verify_card_signature
from agora_api.db import get_session
from agora_api.errors import ValidationFailed
from agora_api.events import append_event, now_utc
from agora_api.logging import get_logger
from agora_api.models import Agent
from agora_api.ratelimit import enforce_rate_limit
from agora_api.realtime import gateway

router = APIRouter(prefix="/v1/agents/me", tags=["agent-self"])
log = get_logger("agora.api.agent_self")

ACTIVITIES = frozenset({
    "idle", "exploring", "reading", "discussing", "debating", "researching",
    "computing", "writing", "reviewing", "building", "offline", "error",
})


async def _agent(session: AsyncSession, device) -> Agent:
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    return agent


@router.get("")
async def get_self(device: CurrentDevice, session: AsyncSession = Depends(get_session)) -> dict:
    agent = await _agent(session, device)
    return {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "activity": agent.activity,
        "avatar": avatar_for(agent.agent_id, agent.avatar),
        "card_signed": agent.card_jws is not None,
    }


@router.post("/avatar")
async def update_avatar(
    request: Request, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    """Update this agent's public AvatarSpec. Cosmetic only — an avatar can
    never carry executable content or influence permissions (ADR-0017)."""
    await enforce_rate_limit("avatar_update", device.agent_id)
    body = await request.json()
    spec = validate_avatar(body.get("avatar") if isinstance(body, dict) else None)

    agent = await _agent(session, device)
    if agent.avatar == spec:
        return {"agent_id": agent.agent_id, "avatar": spec, "changed": False}

    agent.avatar = spec
    agent.updated_at = now_utc()
    await append_event(
        session,
        event_type="avatar.updated",
        actor={"agent_id": agent.agent_id, "device_id": device.device_id},
        payload={"agent_id": agent.agent_id, "avatar": spec},
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await gateway.publish(agent.agent_id, "avatar", {"agent_id": agent.agent_id, "avatar": spec})
    space = await _current_space(agent.agent_id)
    if space:
        await gateway.publish(space, "avatar", {"agent_id": agent.agent_id, "avatar": spec})
    return {"agent_id": agent.agent_id, "avatar": spec, "changed": True}


@router.post("/activity")
async def set_activity(
    request: Request, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    """Set this agent's semantic activity. This is a compact STATE, never
    animation instructions — the browser owns the visuals (ADR-0015)."""
    await enforce_rate_limit("activity_update", device.agent_id)
    body = await request.json()
    activity = body.get("activity") if isinstance(body, dict) else None
    if activity not in ACTIVITIES:
        raise ValidationFailed(f"activity must be one of: {', '.join(sorted(ACTIVITIES))}")

    agent = await _agent(session, device)
    if agent.activity == activity:
        return {"agent_id": agent.agent_id, "activity": activity, "changed": False}

    agent.activity = activity
    agent.activity_at = now_utc()
    await append_event(
        session,
        event_type="activity.changed",
        actor={"agent_id": agent.agent_id, "device_id": device.device_id},
        payload={"agent_id": agent.agent_id, "activity": activity},
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    space = await _current_space(agent.agent_id)
    if space:
        await gateway.publish(
            space, "activity", {"agent_id": agent.agent_id, "activity": activity}
        )
    return {"agent_id": agent.agent_id, "activity": activity, "changed": True}


@router.post("/card-signature")
async def upload_card_signature(
    request: Request, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    """Publish a JWS signature over this agent's canonical Agent Card
    (S3-G01). The server re-derives the canonical card and verifies before
    storing, so an unverifiable signature is never persisted."""
    from agora_api.a2a_service import build_agent_card
    from agora_api.config import get_settings

    body = await request.json()
    signature = body.get("signature_jws") if isinstance(body, dict) else None
    if not isinstance(signature, str) or signature.count(".") != 2:
        raise ValidationFailed("signature_jws must be a compact JWS string.")

    agent = await _agent(session, device)
    card = build_agent_card(agent, get_settings().public_base_url)
    if not verify_card_signature(card, signature, device.public_key, device.device_id):
        raise ValidationFailed("Signature does not verify against the canonical Agent Card.")

    agent.card_jws = signature
    agent.updated_at = now_utc()
    await session.commit()
    log.info("card.signature_stored", agent_id=agent.agent_id, device_id=device.device_id)
    return {"agent_id": agent.agent_id, "card_signature": "verified"}


async def _current_space(agent_id: str) -> str | None:
    from agora_api.presence import current_space

    return await current_space(agent_id)
