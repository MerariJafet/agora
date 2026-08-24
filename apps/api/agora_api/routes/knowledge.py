"""Knowledge Fabric API (Sprint 07)."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.db import get_session
from agora_api.errors import NotFound
from agora_api.knowledge_service import (
    create_verified_evidence_from_snapshot,
    pulse_view,
    search,
    snapshot_view,
    source_view,
    validate_snapshot_evidence_request,
)
from agora_api.models import KnowledgeSnapshot, KnowledgeSource, WorldPulseEvent
from agora_api.ratelimit import enforce_rate_limit
from agora_api.realtime import gateway

router = APIRouter(tags=["knowledge"])


@router.get("/v1/knowledge/sources")
async def list_sources(
    session: AsyncSession = Depends(get_session),
    domain: str | None = Query(default=None),
) -> dict:
    query = select(KnowledgeSource).where(KnowledgeSource.enabled.is_(True))
    if domain:
        query = query.where(KnowledgeSource.domain == domain)
    rows = (
        await session.execute(query.order_by(KnowledgeSource.domain, KnowledgeSource.name))
    ).scalars().all()
    return {"sources": [source_view(source) for source in rows]}


@router.post("/v1/knowledge/search", status_code=201)
async def post_search(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("knowledge_search", device.agent_id)
    body = await request.json()
    snapshot = await search(
        session,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    view = snapshot_view(snapshot)
    await gateway.publish("knowledge", "knowledge", {"event": "snapshot_created", **view})
    if snapshot.result.get("source") in {"gdelt_world_pulse", "nasa_public"}:
        await gateway.publish("world-pulse", "knowledge", {"event": "pulse_updated", **view})
    return view


@router.get("/v1/knowledge/snapshots/{snapshot_id}")
async def get_snapshot(snapshot_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    snapshot = await session.get(KnowledgeSnapshot, snapshot_id)
    if snapshot is None:
        raise NotFound("Knowledge snapshot not found.")
    return snapshot_view(snapshot)


@router.post("/v1/knowledge/snapshots/{snapshot_id}/evidence", status_code=201)
async def post_snapshot_evidence(
    snapshot_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_snapshot_evidence_request(body)
    snapshot = await session.get(KnowledgeSnapshot, snapshot_id)
    if snapshot is None:
        raise NotFound("Knowledge snapshot not found.")
    evidence = await create_verified_evidence_from_snapshot(
        session,
        snapshot=snapshot,
        agent_id=device.agent_id,
        role=body.get("role", "context"),
        claim_id=body.get("claim_id"),
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return evidence


@router.get("/v1/world-pulse/events")
async def list_world_pulse_events(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    rows = (
        await session.execute(
            select(WorldPulseEvent).order_by(desc(WorldPulseEvent.updated_at)).limit(limit)
        )
    ).scalars().all()
    return {"events": [pulse_view(event) for event in rows]}

