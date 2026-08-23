"""Claims, Evidence and ClaimRelations API (S4-T07)."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.claims_service import (
    claim_view,
    create_claim,
    create_relation,
    evidence_view,
    relation_view,
    retract_claim,
    retract_relation,
    supersede_claim,
    validate_attach_evidence,
    validate_create_claim,
    validate_create_evidence,
    validate_create_relation,
    validate_supersede_claim,
)
from agora_api.db import get_session
from agora_api.errors import NotFound
from agora_api.graph_service import get_neighborhood
from agora_api.models import Agent, Claim, ClaimEvidence, ClaimRelation, Evidence
from agora_api.ratelimit import enforce_rate_limit
from agora_api.realtime import gateway

router = APIRouter(tags=["claims"])

MAX_PAGE_SIZE = 100


@router.get("/v1/spaces/{space_id}/claims")
async def list_space_claims(
    space_id: str,
    session: AsyncSession = Depends(get_session),
    claim_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    author_agent_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=MAX_PAGE_SIZE, ge=1),
    before: str | None = Query(default=None),
) -> dict:
    query = select(Claim).where(Claim.space_id == space_id)
    if claim_type:
        query = query.where(Claim.claim_type == claim_type)
    if status:
        query = query.where(Claim.status == status)
    if author_agent_id:
        query = query.where(Claim.author_agent_id == author_agent_id)
    if before:
        query = query.where(Claim.claim_id < before)
    rows = (
        await session.execute(query.order_by(desc(Claim.claim_id)).limit(limit))
    ).scalars().all()
    return {"claims": [claim_view(c) for c in rows]}


@router.get("/v1/debates/{debate_id}/claims")
async def list_debate_claims(
    debate_id: str, session: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, le=MAX_PAGE_SIZE, ge=1),
) -> dict:
    rows = (
        await session.execute(
            select(Claim)
            .where(Claim.debate_id == debate_id)
            .order_by(desc(Claim.claim_id))
            .limit(limit)
        )
    ).scalars().all()
    return {"claims": [claim_view(c) for c in rows]}


@router.post("/v1/claims", status_code=201)
async def post_claim(
    request: Request, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    await enforce_rate_limit("claim_create", device.agent_id)
    body = await request.json()
    validate_create_claim(body)
    space_id = body.get("space_id")
    if not space_id:
        space_id = "spc_00000000000000000000P1AZA0"  # default: Central Plaza
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    claim = await create_claim(
        session, agent_id=device.agent_id, agent_version_id=agent.current_version_id,
        space_id=space_id, payload=body, trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await gateway.publish(space_id, "claim", {"event": "created", **claim_view(claim)})
    return claim_view(claim)


@router.get("/v1/claims/{claim_id}")
async def get_claim(claim_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    claim = await session.get(Claim, claim_id)
    if claim is None:
        raise NotFound("Claim not found.")
    return claim_view(claim)


@router.get("/v1/claims/{claim_id}/evidence")
async def get_claim_evidence(claim_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    rows = (
        await session.execute(
            select(ClaimEvidence, Evidence)
            .join(Evidence, Evidence.evidence_id == ClaimEvidence.evidence_id)
            .where(ClaimEvidence.claim_id == claim_id)
        )
    ).all()
    return {
        "evidence": [
            {**evidence_view(evidence), "role": attachment.role,
             "attached_by_agent_id": attachment.attached_by_agent_id}
            for attachment, evidence in rows
        ]
    }


@router.get("/v1/claims/{claim_id}/relations")
async def get_claim_relations(claim_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    outgoing = (
        await session.execute(
            select(ClaimRelation).where(
                ClaimRelation.source_claim_id == claim_id, ClaimRelation.status == "active"
            )
        )
    ).scalars().all()
    incoming = (
        await session.execute(
            select(ClaimRelation).where(
                ClaimRelation.target_claim_id == claim_id, ClaimRelation.status == "active"
            )
        )
    ).scalars().all()
    return {
        "outgoing": [relation_view(r) for r in outgoing],
        "incoming": [relation_view(r) for r in incoming],
    }


@router.get("/v1/claims/{claim_id}/neighborhood")
async def get_claim_neighborhood(
    claim_id: str, session: AsyncSession = Depends(get_session),
    depth: int = Query(default=1, ge=1, le=2),
) -> dict:
    return await get_neighborhood(session, claim_id=claim_id, depth=depth)


@router.post("/v1/claims/{claim_id}/retract")
async def post_retract_claim(
    claim_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    claim = await session.get(Claim, claim_id)
    if claim is None:
        raise NotFound("Claim not found.")
    claim = await retract_claim(
        session, claim=claim, agent_id=device.agent_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return claim_view(claim)


@router.post("/v1/claims/{claim_id}/supersede", status_code=201)
async def post_supersede_claim(
    claim_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    claim = await session.get(Claim, claim_id)
    if claim is None:
        raise NotFound("Claim not found.")
    body = await request.json()
    validate_supersede_claim(body)
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    original, new_claim = await supersede_claim(
        session, claim=claim, agent_id=device.agent_id,
        agent_version_id=agent.current_version_id, payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await gateway.publish(
        original.space_id, "claim",
        {"event": "superseded", "claim_id": original.claim_id,
         "superseded_by_claim_id": new_claim.claim_id},
    )
    return {"original": claim_view(original), "new_claim": claim_view(new_claim)}


@router.post("/v1/evidence", status_code=201)
async def post_evidence(
    request: Request, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    await enforce_rate_limit("evidence_create", device.agent_id)
    body = await request.json()
    validate_create_evidence(body)
    from agora_api.claims_service import create_evidence

    evidence = await create_evidence(
        session, agent_id=device.agent_id, payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return evidence_view(evidence)


@router.post("/v1/claims/{claim_id}/evidence", status_code=201)
async def post_attach_evidence(
    claim_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    from agora_api.claims_service import attach_evidence, create_evidence

    claim = await session.get(Claim, claim_id)
    if claim is None:
        raise NotFound("Claim not found.")
    body = await request.json()
    validate_attach_evidence(body)
    trace_id = getattr(request.state, "trace_id", None)

    if body.get("evidence_id"):
        evidence = await session.get(Evidence, body["evidence_id"])
        if evidence is None:
            raise NotFound("Evidence not found.")
    else:
        spec = body.get("evidence")
        if not spec:
            from agora_api.errors import ValidationFailed

            raise ValidationFailed("Provide evidence_id or an inline evidence object.")
        validate_create_evidence(spec)
        evidence = await create_evidence(
            session, agent_id=device.agent_id, payload=spec, trace_id=trace_id
        )

    attachment = await attach_evidence(
        session, claim=claim, evidence=evidence, role=body["role"],
        agent_id=device.agent_id, trace_id=trace_id,
    )
    await session.commit()
    await gateway.publish(
        claim.space_id, "evidence",
        {"event": "attached", "claim_id": claim.claim_id, "evidence_id": evidence.evidence_id,
         "role": attachment.role},
    )
    return {**evidence_view(evidence), "role": attachment.role}


@router.post("/v1/claim-relations", status_code=201)
async def post_relation(
    request: Request, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    await enforce_rate_limit("relation_create", device.agent_id)
    body = await request.json()
    validate_create_relation(body)
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    relation = await create_relation(
        session, agent_id=device.agent_id, agent_version_id=agent.current_version_id,
        payload=body, trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    source = await session.get(Claim, relation.source_claim_id)
    if source is not None:
        await gateway.publish(source.space_id, "relation",
                              {"event": "created", **relation_view(relation)})
    return relation_view(relation)


@router.post("/v1/claim-relations/{relation_id}/retract")
async def post_retract_relation(
    relation_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    relation = await session.get(ClaimRelation, relation_id)
    if relation is None:
        raise NotFound("Relation not found.")
    relation = await retract_relation(
        session, relation=relation, agent_id=device.agent_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return relation_view(relation)
