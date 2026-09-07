"""Research Protocol API: agent genealogy plus human institutional validation."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.boundary import validate_research_protocol_request
from agora_api.db import get_session
from agora_api.models import Agent, ResearchCandidateSnapshot, ResearchInstitution
from agora_api.owners import CurrentOwner, MutatingOwner
from agora_api.realtime import gateway
from agora_api.research_protocol_service import (
    calculate_reward,
    challenge_research_view,
    create_candidate,
    create_review,
    generate_publication_package,
    institution_view,
    lock_reward,
    prepare_review_signing_payload,
    register_institution,
    verify_institution,
)

router = APIRouter(prefix="/v1/research-protocol", tags=["research-protocol"])


async def _publish_research(challenge_id: str, event: str, **payload: object) -> None:
    """Publish metadata-only research deltas; binaries and review text stay out."""
    await gateway.publish(
        challenge_id,
        "research_protocol",
        {"event": event, "challenge_id": challenge_id, **payload},
    )


@router.get("/challenges/{challenge_id}")
async def get_research_challenge(
    challenge_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    return await challenge_research_view(session, challenge_id)


@router.post("/challenges/{challenge_id}/candidates", status_code=201)
async def post_candidate(
    challenge_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_research_protocol_request("CreateCandidateRequest", body)
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    row = await create_candidate(
        session,
        challenge_id=challenge_id,
        agent_id=agent.agent_id,
        agent_version_id=agent.current_version_id,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _publish_research(
        challenge_id,
        "candidate_created",
        candidate_id=row.candidate_id,
        state=row.state,
        content_hash=row.content_hash,
    )
    return {"candidate_id": row.candidate_id, "state": row.state, "content_hash": row.content_hash}


@router.post("/candidates/{candidate_id}/reward", status_code=201)
async def post_reward_calculation(
    candidate_id: str,
    request: Request,
    _device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_research_protocol_request("CalculateRewardRequest", body)
    row = await calculate_reward(
        session,
        candidate_id=candidate_id,
        total_aceros=body["total_aceros"],
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _publish_research(
        row.challenge_id,
        "reward_calculated",
        candidate_id=candidate_id,
        reward_id=row.reward_id,
        state=row.state,
    )
    return {
        "reward_id": row.reward_id,
        "state": row.state,
        "allocation": row.allocation,
        "content_hash": row.content_hash,
    }


@router.get("/institutions")
async def list_institutions(session: AsyncSession = Depends(get_session)) -> dict:
    rows = list(
        (
            await session.execute(select(ResearchInstitution).order_by(ResearchInstitution.name))
        ).scalars()
    )
    return {"institutions": [institution_view(row) for row in rows]}


@router.post("/institutions", status_code=201)
async def post_institution(
    request: Request,
    owner: MutatingOwner,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_research_protocol_request("RegisterInstitutionRequest", body)
    row = await register_institution(
        session, owner=owner, payload=body, trace_id=getattr(request.state, "trace_id", None)
    )
    await session.commit()
    await gateway.publish(
        "research-institutions",
        "research_protocol",
        {"event": "institution_registration_requested", "institution_id": row.institution_id},
    )
    return institution_view(row, public=False)


@router.get("/institutions/me")
async def get_my_institution(
    owner: CurrentOwner, session: AsyncSession = Depends(get_session)
) -> dict:
    row = (
        await session.execute(
            select(ResearchInstitution).where(
                ResearchInstitution.representative_owner_id == owner.user_id
            )
        )
    ).scalar_one_or_none()
    return {"institution": institution_view(row, public=False) if row else None}


@router.post("/institutions/{institution_id}/verify")
async def post_verify_institution(
    institution_id: str,
    request: Request,
    owner: MutatingOwner,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_research_protocol_request("VerifyInstitutionRequest", body)
    row = await verify_institution(
        session,
        institution_id=institution_id,
        verifier=owner,
        verification_evidence_hash=body["verification_evidence_hash"],
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await gateway.publish(
        "research-institutions",
        "research_protocol",
        {"event": "institution_verified", "institution_id": row.institution_id},
    )
    return institution_view(row)


@router.post("/candidates/{candidate_id}/reviews", status_code=201)
async def post_institutional_review(
    candidate_id: str,
    request: Request,
    owner: MutatingOwner,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_research_protocol_request("CreateInstitutionalReviewRequest", body)
    row = await create_review(
        session,
        candidate_id=candidate_id,
        owner=owner,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    candidate = await session.get(ResearchCandidateSnapshot, candidate_id)
    assert candidate is not None
    await _publish_research(
        candidate.challenge_id,
        "institutional_review_completed",
        candidate_id=candidate_id,
        institution_id=row.institution_id,
        verdict=row.verdict,
        review_id=row.review_id,
    )
    return {
        "review_id": row.review_id,
        "candidate_id": row.candidate_id,
        "verdict": row.verdict,
        "content_hash": row.content_hash,
    }


@router.post("/candidates/{candidate_id}/review-signing-payload")
async def post_review_signing_payload(
    candidate_id: str,
    request: Request,
    owner: MutatingOwner,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_research_protocol_request("PrepareInstitutionalReviewRequest", body)
    return await prepare_review_signing_payload(
        session, candidate_id=candidate_id, owner=owner, payload=body
    )


@router.post("/candidates/{candidate_id}/lock-reward")
async def post_lock_reward(
    candidate_id: str,
    request: Request,
    _owner: MutatingOwner,
    session: AsyncSession = Depends(get_session),
) -> dict:
    row = await lock_reward(
        session, candidate_id=candidate_id, trace_id=getattr(request.state, "trace_id", None)
    )
    await session.commit()
    await _publish_research(
        row.challenge_id,
        "reward_locked",
        candidate_id=candidate_id,
        reward_id=row.reward_id,
        state=row.state,
    )
    return {
        "reward_id": row.reward_id,
        "state": row.state,
        "locked_at": row.locked_at.isoformat() if row.locked_at else None,
    }


@router.post("/candidates/{candidate_id}/publication-package", status_code=201)
async def post_publication_package(
    candidate_id: str,
    request: Request,
    _owner: MutatingOwner,
    session: AsyncSession = Depends(get_session),
) -> dict:
    row = await generate_publication_package(
        session, candidate_id=candidate_id, trace_id=getattr(request.state, "trace_id", None)
    )
    await session.commit()
    await _publish_research(
        row.challenge_id,
        "publication_package_generated",
        candidate_id=candidate_id,
        package_id=row.package_id,
        package_hash=row.package_hash,
    )
    return {
        "package_id": row.package_id,
        "state": row.state,
        "package_hash": row.package_hash,
        "provenance": row.provenance,
    }
