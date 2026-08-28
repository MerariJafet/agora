"""Formal world opportunity market routes."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.db import get_session
from agora_api.models import (
    Agent,
    WorldNeed,
    WorldOffer,
    WorldOpportunity,
)
from agora_api.ratelimit import enforce_rate_limit
from agora_api.realtime import gateway
from agora_api.world_market_service import (
    accept_commitment,
    commitment_view,
    contribution_view,
    create_need,
    create_offer,
    create_opportunity,
    deliver_contribution,
    market_summary,
    need_view,
    offer_view,
    opportunity_view,
    outcome_view,
    preference_evidence,
    propose_commitment,
    record_outcome,
    validate_create_need,
    validate_create_offer,
    validate_create_opportunity,
    validate_deliver_contribution,
    validate_propose_commitment,
    validate_record_outcome,
)

router = APIRouter(prefix="/v1/world-market", tags=["world-market"])


async def _agent_for_device(session: AsyncSession, device: CurrentDevice) -> Agent:
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    return agent


async def _fan_out(scope: str, event: dict) -> None:
    await gateway.publish(scope, "world_market", event)


@router.get("")
async def get_market_summary(session: AsyncSession = Depends(get_session)) -> dict:
    return await market_summary(session)


@router.get("/opportunities")
async def list_opportunities(
    session: AsyncSession = Depends(get_session),
    district_id: str | None = None,
    state: str | None = Query(default="open"),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    query = select(WorldOpportunity).where(WorldOpportunity.market_class == "test")
    if district_id:
        query = query.where(WorldOpportunity.district_id == district_id)
    if state:
        query = query.where(WorldOpportunity.state == state)
    rows = (
        (await session.execute(query.order_by(WorldOpportunity.created_at.desc()).limit(limit)))
        .scalars()
        .all()
    )
    return {"opportunities": [opportunity_view(row) for row in rows]}


@router.get("/needs")
async def list_needs(
    session: AsyncSession = Depends(get_session),
    district_id: str | None = None,
    state: str | None = Query(default="open"),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    query = select(WorldNeed).where(WorldNeed.market_class == "test")
    if district_id:
        query = query.where(WorldNeed.district_id == district_id)
    if state:
        query = query.where(WorldNeed.state == state)
    rows = (
        (await session.execute(query.order_by(WorldNeed.created_at.desc()).limit(limit)))
        .scalars()
        .all()
    )
    return {"needs": [need_view(row) for row in rows]}


@router.get("/offers")
async def list_offers(
    session: AsyncSession = Depends(get_session),
    district_id: str | None = None,
    state: str | None = Query(default="open"),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    query = select(WorldOffer).where(WorldOffer.market_class == "test")
    if district_id:
        query = query.where(WorldOffer.district_id == district_id)
    if state:
        query = query.where(WorldOffer.state == state)
    rows = (
        (await session.execute(query.order_by(WorldOffer.created_at.desc()).limit(limit)))
        .scalars()
        .all()
    )
    return {"offers": [offer_view(row) for row in rows]}


@router.post("/opportunities", status_code=201)
async def post_opportunity(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("world_market_mutation", device.agent_id)
    body = await request.json()
    validate_create_opportunity(body)
    agent = await _agent_for_device(session, device)
    row, event_id = await create_opportunity(
        session, agent=agent, payload=body, trace_id=getattr(request.state, "trace_id", None)
    )
    await session.commit()
    await _fan_out(
        row.district_id,
        {"event": "opportunity_created", **opportunity_view(row, event_id)},
    )
    return opportunity_view(row, event_id)


@router.post("/needs", status_code=201)
async def post_need(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("world_market_mutation", device.agent_id)
    body = await request.json()
    validate_create_need(body)
    agent = await _agent_for_device(session, device)
    row, event_id = await create_need(
        session, agent=agent, payload=body, trace_id=getattr(request.state, "trace_id", None)
    )
    await session.commit()
    await _fan_out(
        row.district_id,
        {"event": "need_created", **need_view(row, event_id)},
    )
    return need_view(row, event_id)


@router.post("/offers", status_code=201)
async def post_offer(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("world_market_mutation", device.agent_id)
    body = await request.json()
    validate_create_offer(body)
    agent = await _agent_for_device(session, device)
    row, event_id = await create_offer(
        session, agent=agent, payload=body, trace_id=getattr(request.state, "trace_id", None)
    )
    await session.commit()
    await _fan_out(
        row.district_id,
        {"event": "offer_created", **offer_view(row, event_id)},
    )
    return offer_view(row, event_id)


@router.post("/commitments", status_code=201)
async def post_commitment(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("world_market_mutation", device.agent_id)
    body = await request.json()
    validate_propose_commitment(body)
    agent = await _agent_for_device(session, device)
    row, event_id = await propose_commitment(
        session, agent=agent, payload=body, trace_id=getattr(request.state, "trace_id", None)
    )
    await session.commit()
    await _fan_out(
        row.commitment_id,
        {"event": "commitment_proposed", **commitment_view(row, event_id)},
    )
    return commitment_view(row, event_id)


@router.post("/commitments/{commitment_id}/accept")
async def post_accept_commitment(
    commitment_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("world_market_mutation", device.agent_id)
    agent = await _agent_for_device(session, device)
    row, event_id = await accept_commitment(
        session,
        commitment_id=commitment_id,
        agent=agent,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _fan_out(
        row.commitment_id,
        {"event": "commitment_accepted", **commitment_view(row, event_id)},
    )
    return commitment_view(row, event_id)


@router.post("/contributions", status_code=201)
async def post_contribution(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("world_market_mutation", device.agent_id)
    body = await request.json()
    validate_deliver_contribution(body)
    agent = await _agent_for_device(session, device)
    row, event_id = await deliver_contribution(
        session, agent=agent, payload=body, trace_id=getattr(request.state, "trace_id", None)
    )
    await session.commit()
    await _fan_out(
        row.commitment_id,
        {"event": "contribution_delivered", **contribution_view(row, event_id)},
    )
    return contribution_view(row, event_id)


@router.post("/contributions/{contribution_id}/outcomes", status_code=201)
async def post_outcome(
    contribution_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("world_market_mutation", device.agent_id)
    body = await request.json()
    validate_record_outcome(body)
    agent = await _agent_for_device(session, device)
    row, event_id = await record_outcome(
        session,
        contribution_id=contribution_id,
        agent=agent,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _fan_out(
        row.contribution_id,
        {"event": "outcome_recorded", **outcome_view(row, event_id)},
    )
    return outcome_view(row, event_id)


@router.get("/agents/{agent_id}/preference-evidence")
async def get_preference_evidence(
    agent_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await preference_evidence(session, agent_id)
