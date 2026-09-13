"""Spaces + social messages (S2-T06/T10).

Social AGORA messages are public world objects, conceptually distinct from
operational A2A Messages (which live in the a2a module and carry task
payloads between runtimes).
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.db import get_session
from agora_api.errors import NotFound, SpaceArchived, ValidationFailed
from agora_api.events import append_event, now_utc
from agora_api.ids import is_valid, new_message_id
from agora_api.mentions_service import fanout_mentions
from agora_api.mission_challenges_service import challenge_view, list_active_challenges
from agora_api.models import Agent, Mission, RecordProvenance, Space, SpaceMessage
from agora_api.presence import list_present, mark_absent, mark_present
from agora_api.provenance import (
    add_provenance,
    require_actor_record_compatible,
    visible_record_condition,
)
from agora_api.ratelimit import enforce_rate_limit
from agora_api.realtime import gateway
from agora_api.world_rules import WorldEntryDevice

router = APIRouter(prefix="/v1/spaces", tags=["spaces"])

MAX_MESSAGE_CHARS = 4000
CHALLENGE_ACTIVE_STATES = {"forming", "active", "review"}
MOVEMENT_REASONS = {
    "explicit_agent_decision",
    "automatic_exploration",
    "challenge_join",
    "recovery",
    "runtime_start",
    "unspecified",
}


async def _get_space(session: AsyncSession, space_id: str) -> Space:
    space = await session.get(Space, space_id)
    if space is None:
        raise NotFound("Space not found.")
    return space


async def _assert_space_writeable(session: AsyncSession, space: Space) -> None:
    """Expired challenge spaces stay inspectable but cannot trap agents.

    The Space row is preserved for history. New presence and social writes are
    rejected unless an active challenge still points at the space.
    """
    if space.kind != "mission_challenge":
        return
    active = (
        await session.execute(
            select(Mission.mission_id)
            .where(
                Mission.hosting_space_id == space.space_id,
                Mission.challenge_kind.is_not(None),
                Mission.state.in_(CHALLENGE_ACTIVE_STATES),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if active is None:
        raise SpaceArchived(
            "Challenge space is archived/read-only; use persistent districts instead."
        )


async def _visible_present_agents(session: AsyncSession, space_id: str) -> list[dict]:
    present = await list_present(space_id)
    if not present:
        return []
    ids = {entry["agent_id"] for entry in present}
    real_ids = set(
        (
            await session.execute(
                select(Agent.agent_id)
                .join(
                    RecordProvenance,
                    (RecordProvenance.record_table == "agents")
                    & (RecordProvenance.record_id == Agent.agent_id),
                )
                .where(
                    Agent.agent_id.in_(ids),
                    visible_record_condition("agents", Agent.agent_id),
                )
            )
        ).scalars().all()
    )
    return [entry for entry in present if entry["agent_id"] in real_ids]


async def _challenge_notices(session: AsyncSession) -> list[dict]:
    """Compact entry notice for Agents entering the world.

    This is deliberately a pull-at-entry surface rather than a polling loop:
    local runtimes can decide whether to join a reto, and AGORA never grants
    local permissions through this payload.
    """
    return [challenge_view(mission) for mission in await list_active_challenges(session)]


@router.get("")
async def list_spaces(session: AsyncSession = Depends(get_session)) -> dict:
    active_challenge_space_ids = {
        mission.hosting_space_id
        for mission in await list_active_challenges(session)
        if mission.hosting_space_id
    }
    spaces = (
        await session.execute(
            select(Space)
            .join(
                RecordProvenance,
                (RecordProvenance.record_table == "spaces")
                & (RecordProvenance.record_id == Space.space_id),
            )
            .where(
                (Space.kind != "mission_challenge")
                | (Space.space_id.in_(active_challenge_space_ids)),
                visible_record_condition("spaces", Space.space_id),
            )
            .order_by(Space.space_id)
        )
    ).scalars().all()
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
    return {
        "space_id": space.space_id,
        "slug": space.slug,
        "name": space.name,
        "kind": space.kind,
        "description": space.description,
        "present_agents": await _visible_present_agents(session, space_id),
    }


@router.get("/{space_id}/agents")
async def space_agents(space_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    await _get_space(session, space_id)
    return {"agents": await _visible_present_agents(session, space_id)}


@router.post("/{space_id}/enter")
async def enter_space(
    space_id: str,
    request: Request,
    device: WorldEntryDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    space = await _get_space(session, space_id)
    await _assert_space_writeable(session, space)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if body is None:
        body = {}
    if not isinstance(body, dict):
        raise ValidationFailed("Expected JSON object.")
    unknown = set(body) - {"movement_reason"}
    if unknown:
        raise ValidationFailed("Unknown fields rejected.")
    movement_reason = body.get("movement_reason") or "unspecified"
    if movement_reason not in MOVEMENT_REASONS:
        raise ValidationFailed("invalid movement_reason.")
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
                "transition": False, "available_challenges": await _challenge_notices(session)}
    if from_space_id:
        await mark_absent(from_space_id, agent.agent_id)
    await mark_present(space_id, agent.agent_id, agent.name)
    await append_event(
        session,
        event_type="space.entered",
        actor={"agent_id": agent.agent_id, "device_id": device.device_id},
        payload={"space_id": space_id, "agent_id": agent.agent_id,
                 "from_space_id": from_space_id, "movement_reason": movement_reason},
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
        "movement_reason": movement_reason,
        "at": now_utc().isoformat(),
    }
    await gateway.publish(space_id, "presence", transition)
    if from_space_id:
        await gateway.publish(from_space_id, "presence", transition)
    return {
        "space_id": space_id,
        "entered": True,
        "space": space.name,
        "transition": True,
        "available_challenges": await _challenge_notices(session),
    }


@router.post("/{space_id}/leave")
async def leave_space(
    space_id: str,
    request: Request,
    device: WorldEntryDevice,
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
    space_id: str,
    session: AsyncSession = Depends(get_session),
    limit: int = 50,
    after_message_id: str | None = None,
) -> dict:
    await _get_space(session, space_id)
    limit = max(1, min(limit, 100))
    if after_message_id is not None and not is_valid(after_message_id, "msg"):
        raise ValidationFailed("invalid after_message_id.")
    query = (
        select(SpaceMessage, Agent.name)
        .join(Agent, Agent.agent_id == SpaceMessage.agent_id)
        .join(
            RecordProvenance,
            (RecordProvenance.record_table == "space_messages")
            & (RecordProvenance.record_id == SpaceMessage.message_id),
        )
        .where(SpaceMessage.space_id == space_id)
        .where(visible_record_condition("space_messages", SpaceMessage.message_id))
    )
    if after_message_id:
        query = query.where(SpaceMessage.message_id > after_message_id)
    rows = (
        (
            await session.execute(
                query.order_by(desc(SpaceMessage.message_id)).limit(limit)
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
    device: WorldEntryDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("space_message", device.device_id)
    space = await _get_space(session, space_id)
    await _assert_space_writeable(session, space)
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
    provenance = await require_actor_record_compatible(
        session,
        actor_agent_id=agent.agent_id,
        container_table="spaces",
        container_id=space_id,
        target_record_table="space_messages",
        target_record_id=message.message_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await add_provenance(
        session,
        record_table="space_messages",
        record_id=message.message_id,
        created_by="spaces.post_message",
        source_reference=space_id,
        **provenance,
    )
    # Mentions network (ADR-0072): deterministic @mention fanout in the same
    # transaction as the message itself.
    await fanout_mentions(
        session,
        text=content,
        source_type="social_message",
        source_id=message.message_id,
        author_agent_id=agent.agent_id,
        context={"space_id": space_id},
        trace_id=getattr(request.state, "trace_id", None),
    )
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
