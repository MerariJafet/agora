"""MAGNA Research Allocation Center routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.db import get_session
from agora_api.models import (
    Agent,
    PriorityAssessment,
    ResearchProposal,
    ResearchProposalInformation,
)
from agora_api.ratelimit import enforce_rate_limit
from agora_api.realtime import gateway
from agora_api.research_market_service import (
    apply_lifecycle_action,
    create_appeal,
    create_commitment,
    create_pool,
    create_priority_assessment,
    create_research_proposal,
    information_view,
    link_duplicate,
    market_snapshot,
    proposal_view,
    provide_research_information,
    review_eligibility,
    run_test_epoch,
    simulate_thirty_days,
    submit_for_eligibility,
)

router = APIRouter(prefix="/v1/research-market", tags=["research-market"])


async def _agent(session: AsyncSession, device: CurrentDevice) -> Agent:
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    return agent


async def _fan_out(scope: str, event: dict) -> None:
    await gateway.publish(scope, "research_market", event)


@router.get("")
async def get_research_market(session: AsyncSession = Depends(get_session)) -> dict:
    return await market_snapshot(session)


@router.get("/proposals")
async def list_research_proposals(
    session: AsyncSession = Depends(get_session),
    world_id: str | None = None,
    state: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    query = select(ResearchProposal)
    if world_id:
        query = query.where(ResearchProposal.world_id == world_id)
    if state:
        query = query.where(ResearchProposal.state == state)
    rows = (
        (await session.execute(query.order_by(ResearchProposal.created_at.desc()).limit(limit)))
        .scalars()
        .all()
    )
    return {"proposals": [proposal_view(row) for row in rows]}


@router.get("/proposals/{proposal_id}")
async def get_research_proposal(
    proposal_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    proposal = await session.get(ResearchProposal, proposal_id)
    if proposal is None:
        from agora_api.errors import NotFound

        raise NotFound("Research proposal not found.")
    assessments = (
        (
            await session.execute(
                select(PriorityAssessment).where(PriorityAssessment.proposal_id == proposal_id)
            )
        )
        .scalars()
        .all()
    )
    information_updates = (
        (
            await session.execute(
                select(ResearchProposalInformation)
                .where(ResearchProposalInformation.proposal_id == proposal_id)
                .order_by(ResearchProposalInformation.new_revision.asc())
            )
        )
        .scalars()
        .all()
    )
    return {
        **proposal_view(proposal),
        "information_updates": [information_view(row) for row in information_updates],
        "assessments": [
            {
                "assessment_id": row.assessment_id,
                "policy_version": row.policy_version,
                "vector": row.vector,
                "uncertainty": row.uncertainty,
                "pareto_layer": row.pareto_layer,
                "portfolio_score": row.portfolio_score,
                "not_truth_score": True,
            }
            for row in assessments
        ],
    }


@router.post("/proposals", status_code=201)
async def post_research_proposal(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("research_market_mutation", device.agent_id)
    body = await request.json()
    agent = await _agent(session, device)
    row = await create_research_proposal(
        session, agent=agent, payload=body, trace_id=getattr(request.state, "trace_id", None)
    )
    await session.commit()
    view = proposal_view(row)
    await _fan_out(row.world_id, {"event": "research_proposal_created", **view})
    return view


@router.post("/proposals/{proposal_id}/information", status_code=201)
async def post_research_information(
    proposal_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("research_market_mutation", device.agent_id)
    body = await request.json()
    agent = await _agent(session, device)
    proposal, update = await provide_research_information(
        session,
        proposal_id=proposal_id,
        agent=agent,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    result = {**proposal_view(proposal), "information_update": information_view(update)}
    await _fan_out(
        proposal.world_id,
        {"event": "research_proposal_information_provided", **result},
    )
    return result


@router.post("/proposals/{proposal_id}/submit-for-eligibility")
async def post_submit_for_eligibility(
    proposal_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("research_market_mutation", device.agent_id)
    agent = await _agent(session, device)
    row = await submit_for_eligibility(
        session,
        proposal_id=proposal_id,
        agent=agent,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    view = proposal_view(row)
    await _fan_out(row.world_id, {"event": "research_proposal_submitted", **view})
    return view


@router.post("/proposals/{proposal_id}/eligibility-reviews", status_code=201)
async def post_eligibility_review(
    proposal_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("research_market_mutation", device.agent_id)
    body = await request.json()
    agent = await _agent(session, device)
    row = await review_eligibility(
        session,
        proposal_id=proposal_id,
        agent=agent,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _fan_out(
        proposal_id, {"event": "research_eligibility_reviewed", "proposal_id": proposal_id}
    )
    return {
        "review_id": row.review_id,
        "proposal_id": row.proposal_id,
        "decision": row.decision,
        "reason_codes": row.reason_codes,
        "gate_results": row.gate_results,
    }


@router.post("/proposals/{proposal_id}/priority-assessments", status_code=201)
async def post_priority_assessment(
    proposal_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("research_market_mutation", device.agent_id)
    body = await request.json()
    agent = await _agent(session, device)
    row = await create_priority_assessment(
        session,
        proposal_id=proposal_id,
        agent=agent,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return {
        "assessment_id": row.assessment_id,
        "proposal_id": row.proposal_id,
        "policy_version": row.policy_version,
        "vector": row.vector,
        "uncertainty": row.uncertainty,
        "pareto_layer": row.pareto_layer,
        "portfolio_score": row.portfolio_score,
        "reason_codes": row.reason_codes,
        "not_truth_score": True,
    }


@router.post("/proposals/{proposal_id}/commitments", status_code=201)
async def post_research_commitment(
    proposal_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("research_market_mutation", device.agent_id)
    body = await request.json()
    agent = await _agent(session, device)
    row = await create_commitment(
        session,
        proposal_id=proposal_id,
        agent=agent,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return {
        "commitment_id": row.commitment_id,
        "proposal_id": row.proposal_id,
        "role": row.role,
        "state": row.state,
        "resource_limits": row.resource_limits,
        "does_not_grant_local_permissions": True,
    }


@router.post("/proposals/{proposal_id}/pools", status_code=201)
async def post_contribution_pool(
    proposal_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("research_market_mutation", device.agent_id)
    body = await request.json()
    agent = await _agent(session, device)
    row = await create_pool(
        session,
        proposal_id=proposal_id,
        agent=agent,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return {
        "pool_id": row.pool_id,
        "proposal_id": row.proposal_id,
        "state": row.state,
        "terms": row.terms,
    }


@router.post("/proposals/{proposal_id}/appeals", status_code=201)
async def post_research_appeal(
    proposal_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("research_market_mutation", device.agent_id)
    body = await request.json()
    agent = await _agent(session, device)
    row = await create_appeal(
        session,
        proposal_id=proposal_id,
        agent=agent,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return {"appeal_id": row.appeal_id, "proposal_id": row.proposal_id, "state": row.state}


@router.post("/proposals/{proposal_id}/duplicate-links", status_code=201)
async def post_duplicate_link(
    proposal_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("research_market_mutation", device.agent_id)
    body = await request.json()
    agent = await _agent(session, device)
    row = await link_duplicate(
        session,
        proposal_id=proposal_id,
        agent=agent,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return {
        "duplicate_link_id": row.duplicate_link_id,
        "source_proposal_id": row.source_proposal_id,
        "target_proposal_id": row.target_proposal_id,
        "link_type": row.link_type,
        "confidence": row.confidence,
        "semantic_result_not_auto_rejection": True,
    }


@router.post("/proposals/{proposal_id}/actions")
async def post_lifecycle_action(
    proposal_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("research_market_mutation", device.agent_id)
    body = await request.json()
    agent = await _agent(session, device)
    row = await apply_lifecycle_action(
        session,
        proposal_id=proposal_id,
        agent=agent,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    view = proposal_view(row)
    await _fan_out(row.world_id, {"event": "research_proposal_lifecycle", **view})
    return view


@router.post("/epochs/test-run")
async def post_test_epoch(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("research_epoch_test", device.agent_id)
    body = await request.json()
    result = await run_test_epoch(
        session, payload=body, trace_id=getattr(request.state, "trace_id", None)
    )
    await session.commit()
    return result


@router.post("/epochs/simulate-30-days")
async def post_simulate_thirty_days(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("research_epoch_test", device.agent_id)
    body = await request.json()
    return await simulate_thirty_days(session, payload=body)
