"""MAGNA Knowledge Ledger API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.db import get_session
from agora_api.errors import NotFound
from agora_api.magna_knowledge_ledger import (
    amend_protocol,
    create_edge,
    create_merkle_batch,
    create_object,
    edge_view,
    get_lineage,
    object_view,
    record_experiment,
    register_protocol,
    resolve_epistemic_state,
    verify_capsule_fixture,
)
from agora_api.models import Agent, MagnaKnowledgeObject, MagnaMerkleBatch, MagnaResolutionReceipt
from agora_api.ratelimit import enforce_rate_limit
from agora_api.realtime import gateway

router = APIRouter(prefix="/v1/knowledge-ledger", tags=["magna-knowledge-ledger"])


async def _agent(session: AsyncSession, device: CurrentDevice) -> Agent:
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    return agent


@router.get("")
async def ledger_snapshot(session: AsyncSession = Depends(get_session)) -> dict:
    counts = (
        await session.execute(
            select(MagnaKnowledgeObject.object_type, MagnaKnowledgeObject.visibility_lane)
            .order_by(MagnaKnowledgeObject.object_type)
        )
    ).all()
    by_type: dict[str, int] = {}
    by_lane: dict[str, int] = {}
    for object_type, lane in counts:
        by_type[object_type] = by_type.get(object_type, 0) + 1
        by_lane[lane] = by_lane.get(lane, 0) + 1
    return {
        "ledger_version": "magna-knowledge-ledger.v1",
        "classification": "public_world_context",
        "runtime_trust": "untrusted_remote",
        "truth_boundary": "epistemic_state_requires_resolution_receipts_not_votes",
        "payment_boundary": "resolution_receipts_do_not_settle_tokoin_in_sprint_03",
        "counts_by_type": by_type,
        "counts_by_lane": by_lane,
    }


@router.get("/objects")
async def list_objects(
    session: AsyncSession = Depends(get_session),
    object_type: str | None = None,
    visibility_lane: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    query = select(MagnaKnowledgeObject)
    if object_type:
        query = query.where(MagnaKnowledgeObject.object_type == object_type)
    if visibility_lane:
        query = query.where(MagnaKnowledgeObject.visibility_lane == visibility_lane)
    rows = (
        await session.execute(query.order_by(desc(MagnaKnowledgeObject.created_at)).limit(limit))
    ).scalars().all()
    return {"objects": [object_view(row) for row in rows]}


@router.post("/objects", status_code=201)
async def post_object(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("knowledge_ledger_mutation", device.agent_id)
    body = await request.json()
    agent = await _agent(session, device)
    row = await create_object(
        session, agent=agent, payload=body, trace_id=getattr(request.state, "trace_id", None)
    )
    await session.commit()
    view = object_view(row)
    await gateway.publish(
        row.world_id or "knowledge",
        "knowledge_ledger",
        {"event": "object_created", **view},
    )
    return view


@router.get("/objects/{object_id}")
async def get_object(object_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    row = await session.get(MagnaKnowledgeObject, object_id)
    if row is None:
        raise NotFound("Knowledge object not found.")
    return object_view(row)


@router.post("/protocols", status_code=201)
async def post_protocol(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("knowledge_ledger_mutation", device.agent_id)
    body = await request.json()
    agent = await _agent(session, device)
    row = await register_protocol(
        session, agent=agent, payload=body, trace_id=getattr(request.state, "trace_id", None)
    )
    await session.commit()
    return object_view(row)


@router.post("/protocols/{protocol_id}/amendments", status_code=201)
async def post_amendment(
    protocol_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("knowledge_ledger_mutation", device.agent_id)
    body = await request.json()
    agent = await _agent(session, device)
    row = await amend_protocol(
        session,
        protocol_id=protocol_id,
        agent=agent,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return object_view(row)


@router.post("/edges", status_code=201)
async def post_edge(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("knowledge_ledger_mutation", device.agent_id)
    body = await request.json()
    agent = await _agent(session, device)
    row = await create_edge(
        session, agent=agent, payload=body, trace_id=getattr(request.state, "trace_id", None)
    )
    await session.commit()
    return edge_view(row)


@router.get("/objects/{object_id}/lineage")
async def get_object_lineage(
    object_id: str,
    session: AsyncSession = Depends(get_session),
    depth: int = Query(default=1, ge=1, le=2),
    limit: int = Query(default=100, ge=1, le=200),
) -> dict:
    return await get_lineage(session, object_id=object_id, depth=depth, limit=limit)


@router.post("/experiments", status_code=201)
async def post_experiment(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("knowledge_ledger_mutation", device.agent_id)
    body = await request.json()
    agent = await _agent(session, device)
    row = await record_experiment(
        session, agent=agent, payload=body, trace_id=getattr(request.state, "trace_id", None)
    )
    await session.commit()
    return object_view(row)


@router.post("/capsules/{capsule_id}/verify")
async def post_capsule_verify(
    capsule_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("knowledge_ledger_mutation", device.agent_id)
    agent = await _agent(session, device)
    result = await verify_capsule_fixture(
        session,
        capsule_id=capsule_id,
        agent=agent,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return result


@router.post("/resolution-receipts", status_code=201)
async def post_resolution_receipt(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("knowledge_ledger_mutation", device.agent_id)
    body = await request.json()
    agent = await _agent(session, device)
    row = await resolve_epistemic_state(
        session, agent=agent, payload=body, trace_id=getattr(request.state, "trace_id", None)
    )
    await session.commit()
    return {
        "receipt_id": row.receipt_id,
        "decision": row.decision,
        "reason_codes": row.reason_codes,
        "requested_state": row.requested_state,
        "payment_eligible": row.payment_eligible,
        "content_hash": row.content_hash,
    }


@router.get("/resolution-receipts/{receipt_id}")
async def get_resolution_receipt(
    receipt_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    row = await session.get(MagnaResolutionReceipt, receipt_id)
    if row is None:
        raise NotFound("Resolution receipt not found.")
    return {
        "receipt_id": row.receipt_id,
        "challenge_id": row.challenge_id,
        "outcome_id": row.outcome_id,
        "registered_protocol_id": row.registered_protocol_id,
        "requested_state": row.requested_state,
        "decision": row.decision,
        "reason_codes": row.reason_codes,
        "evidence_object_ids": row.evidence_object_ids,
        "replication_object_ids": row.replication_object_ids,
        "review_object_ids": row.review_object_ids,
        "unresolved_dissent_ids": row.unresolved_dissent_ids,
        "independence_receipt": row.independence_receipt,
        "content_hash": row.content_hash,
        "payment_eligible": row.payment_eligible,
        "created_at": row.created_at.isoformat().replace("+00:00", "Z"),
    }


@router.post("/merkle-batches", status_code=201)
async def post_merkle_batch(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    agent = await _agent(session, device)
    row = await create_merkle_batch(
        session,
        first_sequence=int(body["first_sequence"]),
        last_sequence=int(body["last_sequence"]),
        agent=agent,
    )
    await session.commit()
    return {
        "batch_id": row.batch_id,
        "first_sequence": row.first_sequence,
        "last_sequence": row.last_sequence,
        "leaf_count": row.leaf_count,
        "merkle_root": row.merkle_root,
        "algorithm": row.algorithm,
        "simulated_anchor_only": True,
    }


@router.get("/merkle-batches/{batch_id}")
async def get_merkle_batch(batch_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    row = await session.get(MagnaMerkleBatch, batch_id)
    if row is None:
        raise NotFound("Merkle batch not found.")
    return {
        "batch_id": row.batch_id,
        "world_instance_id": row.world_instance_id,
        "first_sequence": row.first_sequence,
        "last_sequence": row.last_sequence,
        "leaf_count": row.leaf_count,
        "merkle_root": row.merkle_root,
        "algorithm": row.algorithm,
        "leaves": row.leaves,
        "simulated_anchor_only": True,
    }
