"""MAGNA Sprint 1 constitution, world-charter and release-policy routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.db import get_session
from agora_api.magna_constitution import (
    accept_charter,
    charter_view,
    constitution_view,
    current_charter,
    current_constitution,
    evaluate_rules,
    propose_charter,
    reject_charter_proposal,
    release_policy_view,
    simulate_research_release,
)
from agora_api.models import Agent
from agora_api.ratelimit import enforce_rate_limit

router = APIRouter(tags=["magna-constitution"])


def _etag(value: str) -> str:
    return f'"{value}"'


@router.get("/v1/world/constitution", response_model=None)
async def get_constitution(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict | Response:
    constitution = await current_constitution(session)
    await session.commit()
    etag = _etag(constitution.content_hash)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=304,
            headers={"etag": etag, "cache-control": "public, max-age=300, must-revalidate"},
        )
    response.headers["etag"] = etag
    response.headers["cache-control"] = "public, max-age=300, must-revalidate"
    return constitution_view(constitution)


@router.get("/v1/worlds/{world_id}/charter", response_model=None)
async def get_world_charter(
    world_id: str,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict | Response:
    charter = await current_charter(session, world_id)
    await session.commit()
    etag = _etag(charter.content_hash)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=304,
            headers={"etag": etag, "cache-control": "public, max-age=300, must-revalidate"},
        )
    response.headers["etag"] = etag
    response.headers["cache-control"] = "public, max-age=300, must-revalidate"
    return charter_view(charter)


@router.post("/v1/worlds/{world_id}/charter-proposals", status_code=201)
async def post_charter_proposal(
    world_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("charter_proposal", device.agent_id)
    body = await request.json()
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    proposal = await propose_charter(
        session,
        world_id=world_id,
        agent=agent,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return {
        "proposal_id": proposal.proposal_id,
        "world_id": proposal.world_id,
        "proposal_hash": proposal.proposal_hash,
        "status": proposal.status,
        "created_at": proposal.created_at.isoformat().replace("+00:00", "Z"),
    }


@router.post("/v1/worlds/{world_id}/charter-proposals/{proposal_id}/reject")
async def post_charter_proposal_rejection(
    world_id: str,
    proposal_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("charter_proposal_reject", device.agent_id)
    body = await request.json()
    reason = (
        body.get("reason", "proposer_rejected") if isinstance(body, dict) else "proposer_rejected"
    )
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    proposal = await reject_charter_proposal(
        session,
        world_id=world_id,
        proposal_id=proposal_id,
        agent=agent,
        reason=str(reason),
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return {
        "proposal_id": proposal.proposal_id,
        "world_id": proposal.world_id,
        "status": proposal.status,
        "rejection_reason": proposal.rejection_reason,
    }


@router.post("/v1/worlds/{world_id}/charters/{charter_version}/accept")
async def post_charter_acceptance(
    world_id: str,
    charter_version: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("charter_acceptance", device.agent_id)
    body = await request.json()
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    acceptance = await accept_charter(
        session,
        world_id=world_id,
        charter_version=charter_version,
        device=device,
        agent=agent,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return {
        "acceptance_id": acceptance.acceptance_id,
        "world_id": acceptance.world_id,
        "charter_version": acceptance.charter_version,
        "agent_id": acceptance.agent_id,
        "device_id": acceptance.device_id,
        "charter_hash": acceptance.charter_hash,
        "constitution_hash": acceptance.constitution_hash,
        "accepted_at": acceptance.accepted_at.isoformat().replace("+00:00", "Z"),
        "local_permissions_granted": [],
    }


@router.post("/v1/world/rules/evaluate")
async def post_rule_evaluation(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("rule_evaluation", device.agent_id)
    body = await request.json()
    result = await evaluate_rules(session, device=device, payload=body)
    await session.commit()
    return result


@router.get("/v1/research/release-policy")
async def get_research_release_policy() -> dict:
    return release_policy_view()


@router.post("/v1/research/release-policy/simulate")
async def post_research_release_simulation(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("research_release_simulation", device.agent_id)
    body = await request.json()
    result = await simulate_research_release(session, body)
    await session.commit()
    return result
