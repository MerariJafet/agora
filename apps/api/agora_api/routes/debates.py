"""Debate lifecycle + audience assessment API (S4-T09..T12)."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.db import get_session
from agora_api.debates_service import (
    assessment_summary,
    close_debate,
    create_debate,
    debate_view,
    join_debate,
    set_position,
    upsert_assessment,
    validate_assessment,
    validate_create_debate,
    validate_set_position,
)
from agora_api.errors import NotFound
from agora_api.models import Debate, DebateParticipant, DebatePosition
from agora_api.owners import MutatingOwner
from agora_api.ratelimit import enforce_rate_limit
from agora_api.realtime import gateway

router = APIRouter(tags=["debates"])


async def _positions(session: AsyncSession, debate_id: str) -> list[DebatePosition]:
    return list(
        (
            await session.execute(
                select(DebatePosition)
                .where(DebatePosition.debate_id == debate_id)
                .order_by(DebatePosition.sort_order)
            )
        ).scalars()
    )


@router.get("/v1/spaces/{space_id}/debates")
async def list_space_debates(space_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    rows = (
        await session.execute(select(Debate).where(Debate.space_id == space_id))
    ).scalars().all()
    return {
        "debates": [debate_view(d, await _positions(session, d.debate_id)) for d in rows]
    }


@router.post("/v1/spaces/{space_id}/debates", status_code=201)
async def post_debate(
    space_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("debate_create", device.agent_id)
    body = await request.json()
    validate_create_debate(body)
    debate = await create_debate(
        session, agent_id=device.agent_id, space_id=space_id, payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await gateway.publish(space_id, "debate", {"event": "created", "debate_id": debate.debate_id})
    return debate_view(debate, await _positions(session, debate.debate_id))


@router.get("/v1/debates/{debate_id}")
async def get_debate(debate_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    debate = await session.get(Debate, debate_id)
    if debate is None:
        raise NotFound("Debate not found.")
    participants = (
        await session.execute(
            select(DebateParticipant).where(
                DebateParticipant.debate_id == debate_id,
                DebateParticipant.left_at.is_(None),
            )
        )
    ).scalars().all()
    return {
        **debate_view(debate, await _positions(session, debate_id)),
        "participants": [
            {"agent_id": p.agent_id, "position_id": p.position_id} for p in participants
        ],
    }


@router.post("/v1/debates/{debate_id}/join", status_code=201)
async def post_join(
    debate_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("debate_join", device.agent_id)
    participant = await join_debate(
        session, debate_id=debate_id, agent_id=device.agent_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    debate = await session.get(Debate, debate_id)
    assert debate is not None
    await gateway.publish(
        debate.space_id, "debate",
        {"event": "participant_joined", "debate_id": debate_id, "agent_id": device.agent_id},
    )
    return {"debate_id": debate_id, "agent_id": participant.agent_id,
            "position_id": participant.position_id}


@router.post("/v1/debates/{debate_id}/position")
async def post_position(
    debate_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_set_position(body)
    participant = await set_position(
        session, debate_id=debate_id, agent_id=device.agent_id,
        position_id=body["position_id"], trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    debate = await session.get(Debate, debate_id)
    assert debate is not None
    await gateway.publish(
        debate.space_id, "debate",
        {"event": "position_changed", "debate_id": debate_id, "agent_id": device.agent_id,
         "position_id": participant.position_id},
    )
    return {"debate_id": debate_id, "agent_id": participant.agent_id,
            "position_id": participant.position_id}


@router.post("/v1/debates/{debate_id}/close")
async def post_close(
    debate_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    debate = await session.get(Debate, debate_id)
    if debate is None:
        raise NotFound("Debate not found.")
    debate = await close_debate(
        session, debate=debate, agent_id=device.agent_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await gateway.publish(debate.space_id, "debate", {"event": "closed", "debate_id": debate_id})
    return debate_view(debate, await _positions(session, debate_id))


@router.put("/v1/debates/{debate_id}/assessment/agent")
async def put_agent_assessment(
    debate_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Agent audience assessment — authenticated as the assessing device."""
    await enforce_rate_limit("assessment_agent", device.agent_id)
    debate = await session.get(Debate, debate_id)
    if debate is None:
        raise NotFound("Debate not found.")
    body = await request.json()
    validate_assessment(body)
    await upsert_assessment(
        session, debate=debate, assessor_kind="agent", assessor_id=device.agent_id,
        payload=body, trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    summary = await assessment_summary(session, debate_id=debate_id)
    await gateway.publish(debate.space_id, "assessment",
                          {"debate_id": debate_id, "summary": summary})
    return {"debate_id": debate_id, "recorded": True}


@router.put("/v1/debates/{debate_id}/assessment/human")
async def put_human_assessment(
    debate_id: str, request: Request, owner: MutatingOwner,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Human audience assessment — requires owner cookie session + CSRF
    (SEC-012), same as every other browser-originated mutation."""
    await enforce_rate_limit("assessment_human", owner.user_id)
    debate = await session.get(Debate, debate_id)
    if debate is None:
        raise NotFound("Debate not found.")
    body = await request.json()
    validate_assessment(body)
    await upsert_assessment(
        session, debate=debate, assessor_kind="human", assessor_id=owner.user_id,
        payload=body, trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    summary = await assessment_summary(session, debate_id=debate_id)
    await gateway.publish(debate.space_id, "assessment",
                          {"debate_id": debate_id, "summary": summary})
    return {"debate_id": debate_id, "recorded": True}


@router.get("/v1/debates/{debate_id}/assessment-summary")
async def get_assessment_summary(
    debate_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    if await session.get(Debate, debate_id) is None:
        raise NotFound("Debate not found.")
    return await assessment_summary(session, debate_id=debate_id)
