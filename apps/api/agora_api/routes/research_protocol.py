"""Research Protocol API: agent genealogy plus human and synthetic test validation."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.boundary import validate_research_protocol_request
from agora_api.db import get_session
from agora_api.institutional_validator_service import (
    activate_pilot_validator,
    assign_pilot_validators,
    assignment_package,
    decide_review_proposal,
    own_review_proposal,
    owner_review_proposals,
    register_pilot_validator,
    submit_review_proposal,
    validator_view,
)
from agora_api.institutional_validator_service import (
    commit_review as commit_pilot_review,
)
from agora_api.institutional_validator_service import (
    declare_conflict as declare_pilot_conflict,
)
from agora_api.institutional_validator_service import (
    my_assignments as my_pilot_assignments,
)
from agora_api.institutional_validator_service import (
    panel_view as pilot_panel_view,
)
from agora_api.institutional_validator_service import (
    reveal_review as reveal_pilot_review,
)
from agora_api.models import (
    Agent,
    InstitutionalValidator,
    ResearchCandidateSnapshot,
    ResearchInstitution,
)
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
    reproducibility_package,
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
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_research_protocol_request("CalculateRewardRequest", body)
    row = await calculate_reward(
        session,
        candidate_id=candidate_id,
        agent_id=device.agent_id,
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


@router.get("/institutional-validators")
async def list_pilot_validators(session: AsyncSession = Depends(get_session)) -> dict:
    rows = list(
        (
            await session.execute(
                select(InstitutionalValidator).order_by(InstitutionalValidator.display_name)
            )
        ).scalars()
    )
    return {
        "layer": "Institutional Validation Layer",
        "synthetic_test_only": True,
        "validators": [validator_view(row) for row in rows],
    }


@router.post("/institutional-validators", status_code=201)
async def post_pilot_validator(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_research_protocol_request("RegisterPilotValidatorRequest", body)
    row = await register_pilot_validator(
        session,
        device=device,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return validator_view(row)


@router.post("/institutional-validators/{validator_id}/activate")
async def post_activate_pilot_validator(
    validator_id: str,
    request: Request,
    owner: MutatingOwner,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_research_protocol_request("ActivatePilotValidatorRequest", body)
    row = await activate_pilot_validator(
        session,
        validator_id=validator_id,
        verifier=owner,
        verification_evidence_hash=body["verification_evidence_hash"],
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return validator_view(row)


@router.get("/institutional-validators/me")
async def get_my_pilot_assignments(
    device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    return await my_pilot_assignments(session, device)


@router.post("/candidates/{candidate_id}/pilot-panel", status_code=201)
async def post_pilot_panel(
    candidate_id: str,
    request: Request,
    owner: MutatingOwner,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_research_protocol_request("AssignPilotValidatorsRequest", body)
    await assign_pilot_validators(
        session,
        candidate_id=candidate_id,
        validator_ids=body["validator_ids"],
        decision_owner_id=owner.user_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return await pilot_panel_view(session, candidate_id)


@router.get("/candidates/{candidate_id}/pilot-panel")
async def get_pilot_panel(candidate_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    return await pilot_panel_view(session, candidate_id)


@router.post("/pilot-assignments/{assignment_id}/conflict")
async def post_pilot_conflict(
    assignment_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_research_protocol_request("DeclarePilotConflictRequest", body)
    row = await declare_pilot_conflict(
        session,
        assignment_id=assignment_id,
        device=device,
        declaration=body["conflict_declaration"],
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return {"assignment_id": row.assignment_id, "state": row.state}


@router.get("/pilot-assignments/{assignment_id}/package")
async def get_pilot_assignment_package(
    assignment_id: str,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    package = await assignment_package(session, assignment_id=assignment_id, device=device)
    await session.commit()  # persist the one-time frozen review package
    return package


@router.post("/pilot-assignments/{assignment_id}/proposal", status_code=201)
async def post_pilot_review_proposal(
    assignment_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_research_protocol_request("CreatePilotReviewProposalRequest", body)
    row = await submit_review_proposal(
        session,
        assignment_id=assignment_id,
        device=device,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return {
        "proposal_id": row.proposal_id,
        "proposal_version": row.proposal_version,
        "proposal_hash": row.proposal_hash,
        "state": row.state,
        "synthetic_test_only": True,
        "tokoin_settlement_eligible": False,
    }


@router.get("/pilot-assignments/{assignment_id}/proposal")
async def get_own_pilot_review_proposal(
    assignment_id: str,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await own_review_proposal(session, assignment_id=assignment_id, device=device)


@router.get("/challenges/{challenge_id}/pilot-review-proposals/me")
async def get_owner_pilot_review_proposals(
    challenge_id: str,
    owner: CurrentOwner,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await owner_review_proposals(session, challenge_id=challenge_id, owner=owner)


@router.post("/pilot-review-proposals/{proposal_id}/decision")
async def post_pilot_review_proposal_decision(
    proposal_id: str,
    request: Request,
    owner: MutatingOwner,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_research_protocol_request("DecidePilotReviewProposalRequest", body)
    row = await decide_review_proposal(
        session,
        proposal_id=proposal_id,
        owner=owner,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return {
        "decision_id": row.decision_id,
        "decision": row.decision,
        "proposal_hash": row.proposal_hash,
        "decision_hash": row.decision_hash,
        "synthetic_test_only": True,
        "tokoin_released": False,
    }


@router.post("/pilot-assignments/{assignment_id}/commit")
async def post_pilot_commit(
    assignment_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_research_protocol_request("CommitPilotReviewRequest", body)
    row = await commit_pilot_review(
        session,
        assignment_id=assignment_id,
        device=device,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return {
        "assignment_id": row.assignment_id,
        "state": row.state,
        "commitment_hash": row.commitment_hash,
        "draft_disclosed": False,
    }


@router.post("/pilot-assignments/{assignment_id}/reveal", status_code=201)
async def post_pilot_reveal(
    assignment_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_research_protocol_request("RevealPilotReviewRequest", body)
    review = await reveal_pilot_review(
        session,
        assignment_id=assignment_id,
        device=device,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    panel = await pilot_panel_view(session, review.candidate_id)
    candidate = await session.get(ResearchCandidateSnapshot, review.candidate_id)
    assert candidate is not None
    await _publish_research(
        candidate.challenge_id,
        "pilot_panel_revealed" if panel["all_revealed"] else "pilot_reveal_received",
        candidate_id=review.candidate_id,
        all_revealed=panel["all_revealed"],
        status=panel["status"] if panel["all_revealed"] else "SEALED",
        synthetic_test_only=True,
    )
    return {
        "review_id": review.review_id,
        "review_hash": review.review_hash,
        "panel_status": panel["status"],
        "verdicts_visible": panel["all_revealed"],
    }


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


@router.get("/candidates/{candidate_id}/reproducibility-package")
async def get_reproducibility_package(
    candidate_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    return await reproducibility_package(session, candidate_id)


@router.post('/test-challenges', status_code=201)
async def post_test_challenge(request: Request, device: CurrentDevice,
                             session: AsyncSession = Depends(get_session)) -> dict:
    from pydantic import ValidationError

    from agora_api.errors import ValidationFailed
    from agora_api.ratelimit import enforce_rate_limit
    from agora_api.v03_test_challenges import TestChallengeRequest, create_test_challenge

    await enforce_rate_limit('mission_create', device.agent_id)
    try:
        body = TestChallengeRequest.model_validate(await request.json())
    except (ValueError, ValidationError) as error:
        raise ValidationFailed('Invalid TEST challenge request.') from error
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    result = await create_test_challenge(session, agent, body,
                                        getattr(request.state, 'trace_id', None))
    await session.commit()
    return result
