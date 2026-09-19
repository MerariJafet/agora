"""Delegated university Agent workflow; university approval remains human and signed."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.boundary import validate_research_protocol_request
from agora_api.db import get_session
from agora_api.institution_agent_service import (
    activate_mandate,
    agent_candidate_package,
    agent_candidate_proposal,
    agent_mandate,
    agent_queue,
    decide_proposal,
    owner_mandate,
    owner_proposal,
    prepare_mandate,
    proposal_signing_payload,
    propose_review,
    revoke_mandate,
    submit_signed_review,
)
from agora_api.owners import CurrentOwner, MutatingOwner

router = APIRouter(prefix="/v1/research-protocol", tags=["institution-agent"])


@router.get("/institutions/me/agent-mandate")
async def get_owner_agent_mandate(
    owner: CurrentOwner, session: AsyncSession = Depends(get_session)
) -> dict:
    return await owner_mandate(session, owner=owner)


@router.post("/institutions/me/agent-mandates", status_code=201)
async def post_prepare_agent_mandate(
    request: Request, owner: MutatingOwner, session: AsyncSession = Depends(get_session)
) -> dict:
    body = await request.json()
    validate_research_protocol_request("PrepareInstitutionAgentMandateRequest", body)
    result = await prepare_mandate(
        session,
        owner=owner,
        agent_id=body["agent_id"],
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return result


@router.post("/institutions/me/agent-mandates/{mandate_id}/activate")
async def post_activate_agent_mandate(
    mandate_id: str,
    request: Request,
    owner: MutatingOwner,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_research_protocol_request("ActivateInstitutionAgentMandateRequest", body)
    result = await activate_mandate(
        session,
        owner=owner,
        mandate_id=mandate_id,
        signature=body["signature"],
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return result


@router.post("/institutions/me/agent-mandates/{mandate_id}/revoke")
async def post_revoke_agent_mandate(
    mandate_id: str,
    request: Request,
    owner: MutatingOwner,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_research_protocol_request("RevokeInstitutionAgentMandateRequest", body)
    result = await revoke_mandate(
        session,
        owner=owner,
        mandate_id=mandate_id,
        reason=body["reason"],
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return result


@router.get("/institution-agent/me")
async def get_agent_delegation(
    device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    return await agent_mandate(session, device=device)


@router.get("/institution-agent/me/queue")
async def get_agent_review_queue(
    device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    return await agent_queue(session, device=device)


@router.get("/institution-agent/me/candidates/{candidate_id}/package")
async def get_agent_candidate_package(
    candidate_id: str, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    return await agent_candidate_package(session, device=device, candidate_id=candidate_id)


@router.post("/institution-agent/me/candidates/{candidate_id}/proposal", status_code=201)
async def post_agent_review_proposal(
    candidate_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_research_protocol_request("CreateInstitutionAgentProposalRequest", body)
    result = await propose_review(
        session,
        device=device,
        candidate_id=candidate_id,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return result


@router.get("/institution-agent/me/candidates/{candidate_id}/proposal")
async def get_agent_review_proposal(
    candidate_id: str, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    return await agent_candidate_proposal(session, device=device, candidate_id=candidate_id)


@router.get("/institutions/me/agent-proposals/{candidate_id}")
async def get_owner_agent_proposal(
    candidate_id: str,
    owner: CurrentOwner,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await owner_proposal(session, owner=owner, candidate_id=candidate_id)


@router.post("/institutions/me/agent-proposals/{proposal_id}/signing-payload")
async def get_agent_proposal_signing_payload(
    proposal_id: str,
    request: Request,
    owner: MutatingOwner,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_research_protocol_request("PrepareInstitutionAgentSigningRequest", body)
    return await proposal_signing_payload(
        session, owner=owner, proposal_id=proposal_id, owner_notes=body["owner_notes"]
    )


@router.post("/institutions/me/agent-proposals/{proposal_id}/decision")
async def post_owner_agent_decision(
    proposal_id: str,
    request: Request,
    owner: MutatingOwner,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_research_protocol_request("DecideInstitutionAgentProposalRequest", body)
    result = await decide_proposal(
        session,
        owner=owner,
        proposal_id=proposal_id,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return result


@router.post("/institution-agent/me/proposals/{proposal_id}/submit", status_code=201)
async def post_agent_signed_review(
    proposal_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    review = await submit_signed_review(
        session,
        device=device,
        proposal_id=proposal_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return {
        "review_id": review.review_id,
        "institution_id": review.institution_id,
        "candidate_id": review.candidate_id,
        "verdict": review.verdict,
        "review_hash": review.content_hash,
        "agent_proposal_id": review.agent_proposal_id,
        "tokoin_released": False,
    }
