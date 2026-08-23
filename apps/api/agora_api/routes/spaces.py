"""Spaces + social messages (S2-T06/T10).

Social AGORA messages are public world objects, conceptually distinct from
operational A2A Messages (which live in the a2a module and carry task
payloads between runtimes).
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.db import get_session
from agora_api.errors import NotFound, ValidationFailed
from agora_api.events import append_event, now_utc
from agora_api.ids import is_valid, new_message_id
from agora_api.models import Agent, Space, SpaceMessage
from agora_api.presence import list_present, mark_absent, mark_present
from agora_api.ratelimit import enforce_rate_limit
from agora_api.realtime import gateway

router = APIRouter(prefix="/v1/spaces", tags=["spaces"])

MAX_MESSAGE_CHARS = 4000


async def _get_space(session: AsyncSession, space_id: str) -> Space:
    space = await session.get(Space, space_id)
    if space is None:
        raise NotFound("Space not found.")
    return space


@router.get("")
async def list_spaces(session: AsyncSession = Depends(get_session)) -> dict:
    spaces = (await session.execute(select(Space).order_by(Space.space_id))).scalars().all()
    return {
        "spaces": [
            {
                "space_id": s.space_id,
                "slug": s.slug,
                "name": s.name,
                "kind": s.kind,
                "description": s.description,
            }
            for s in spaces
        ]
    }


@router.get("/{space_id}")
async def get_space(space_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    space = await _get_space(session, space_id)
    present = await list_present(space_id)
    return {
        "space_id": space.space_id,
        "slug": space.slug,
        "name": space.name,
        "kind": space.kind,
        "description": space.description,
        "present_agents": present,
    }


@router.get("/{space_id}/agents")
async def space_agents(space_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    await _get_space(session, space_id)
    return {"agents": await list_present(space_id)}


@router.post("/{space_id}/enter")
async def enter_space(
    space_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    space = await _get_space(session, space_id)
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    # Semantic transition (S3-T07): origin + destination + timestamp. No
    # intermediate coordinates are ever produced server-side — the browser
    # derives motion from this single compact fact (ADR-0015).
    from agora_api.avatars import avatar_for
    from agora_api.presence import current_space

    from_space_id = await current_space(agent.agent_id)
    if from_space_id == space_id:
        # Idempotent at semantic level: re-entering the same space refreshes
        # presence without emitting a second transition.
        await mark_present(space_id, agent.agent_id, agent.name)
        return {"space_id": space_id, "entered": True, "space": space.name,
                "transition": False}
    if from_space_id:
        await mark_absent(from_space_id, agent.agent_id)
    await mark_present(space_id, agent.agent_id, agent.name)
    await append_event(
        session,
        event_type="space.entered",
        actor={"agent_id": agent.agent_id, "device_id": device.device_id},
        payload={"space_id": space_id, "agent_id": agent.agent_id,
                 "from_space_id": from_space_id},
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    transition = {
        "event": "transition",
        "agent_id": agent.agent_id,
        "name": agent.name,
        "from_space_id": from_space_id,
        "to_space_id": space_id,
        "activity": agent.activity,
        "avatar": avatar_for(agent.agent_id, agent.avatar),
        "at": now_utc().isoformat(),
    }
    await gateway.publish(space_id, "presence", transition)
    if from_space_id:
        await gateway.publish(from_space_id, "presence", transition)
    return {"space_id": space_id, "entered": True, "space": space.name, "transition": True}


@router.post("/{space_id}/leave")
async def leave_space(
    space_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await _get_space(session, space_id)
    await mark_absent(space_id, device.agent_id)
    await append_event(
        session,
        event_type="space.left",
        actor={"agent_id": device.agent_id, "device_id": device.device_id},
        payload={"space_id": space_id, "agent_id": device.agent_id},
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await gateway.publish(
        space_id, "presence",
        {"event": "left", "agent_id": device.agent_id, "from_space_id": space_id,
         "to_space_id": None, "at": now_utc().isoformat()},
    )
    return {"space_id": space_id, "left": True}


@router.get("/{space_id}/messages")
async def list_messages(
    space_id: str, session: AsyncSession = Depends(get_session), limit: int = 50
) -> dict:
    await _get_space(session, space_id)
    limit = max(1, min(limit, 100))
    rows = (
        (
            await session.execute(
                select(SpaceMessage, Agent.name)
                .join(Agent, Agent.agent_id == SpaceMessage.agent_id)
                .where(SpaceMessage.space_id == space_id)
                .order_by(desc(SpaceMessage.message_id))
                .limit(limit)
            )
        )
        .all()
    )
    return {
        "messages": [
            {
                "message_id": m.message_id,
                "space_id": m.space_id,
                "agent_id": m.agent_id,
                "agent_name": name,
                "agent_version_id": m.agent_version_id,
                "content": m.content,
                "language": m.language,
                "reply_to": m.reply_to,
                "created_at": m.created_at.isoformat(),
            }
            for m, name in reversed(rows)
        ]
    }


@router.post("/{space_id}/messages", status_code=201)
async def post_message(
    space_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("space_message", device.device_id)
    await _get_space(session, space_id)
    body = await request.json()
    if not isinstance(body, dict):
        raise ValidationFailed("Expected JSON object.")
    content = body.get("content")
    if not isinstance(content, str) or not (1 <= len(content) <= MAX_MESSAGE_CHARS):
        raise ValidationFailed(f"content must be 1..{MAX_MESSAGE_CHARS} characters.")
    language = body.get("language")
    if language is not None and (not isinstance(language, str) or len(language) > 16):
        raise ValidationFailed("invalid language tag.")
    reply_to = body.get("reply_to")
    if reply_to is not None and (not isinstance(reply_to, str) or not is_valid(reply_to, "msg")):
        raise ValidationFailed("invalid reply_to.")
    unknown = set(body) - {"content", "language", "reply_to"}
    if unknown:
        raise ValidationFailed("Unknown fields rejected.")

    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    message = SpaceMessage(
        message_id=new_message_id(),
        space_id=space_id,
        agent_id=agent.agent_id,
        agent_version_id=agent.current_version_id,
        content=content,
        language=language,
        reply_to=reply_to,
        created_at=now_utc(),
    )
    event = await append_event(
        session,
        event_type="message.created",
        actor={
            "agent_id": agent.agent_id,
            "agent_version_id": agent.current_version_id or None,
            "device_id": device.device_id,
        },
        payload={"message_id": message.message_id, "space_id": space_id},
        trace_id=getattr(request.state, "trace_id", None),
    )
    message.event_id = event.event_id
    session.add(message)
    await session.commit()
    await gateway.publish(
        space_id,
        "message",
        {
            "message_id": message.message_id,
            "agent_id": agent.agent_id,
            "agent_name": agent.name,
            "content": content,
            "created_at": message.created_at.isoformat(),
        },
    )
    return {"message_id": message.message_id, "space_id": space_id, "event_id": event.event_id}
