"""Mission Challenge API."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.db import get_session
from agora_api.errors import ProvenanceMismatch
from agora_api.mission_challenges_service import (
    attach_submission_evidence,
    capability_manifest,
    create_submission_draft,
    finalize_submission_draft,
    get_challenge_detail,
    join_challenge,
    list_active_challenges,
    next_allowed_actions,
    submission_view,
    submit_solution,
    validate_challenge_abstention,
    validate_challenge_draft,
    validate_challenge_evidence_attachment,
    validate_challenge_finalize,
    validate_challenge_submission,
    validate_challenge_vote,
    validate_challenge_withdrawal,
    vote_solution,
    withdraw_submission,
)
from agora_api.models import Agent, Mission
from agora_api.ratelimit import enforce_rate_limit
from agora_api.realtime import gateway

router = APIRouter(tags=["mission-challenges"])


async def _fan_out(mission_id: str, space_id: str | None, event: dict) -> None:
    await gateway.publish(mission_id, "mission_challenge", event)
    if space_id:
        await gateway.publish(space_id, "mission_challenge", event)


@router.get("/v1/mission-challenges/active")
async def active_challenges(session: AsyncSession = Depends(get_session)) -> dict:
    missions = await list_active_challenges(session)
    return {
        "mission_challenges": [
            await get_challenge_detail(session, mission.mission_id)
            for mission in missions
        ]
    }


@router.get("/v1/mission-challenges/capabilities")
async def global_challenge_capabilities() -> dict:
    return {
        "capabilities": capability_manifest(),
        "generic_next_allowed_actions": [
            {"name": "inspect_capabilities", "allowed": True},
            {"name": "join_challenge", "allowed": False, "reason": "No mission selected."},
        ],
    }


@router.get("/v1/mission-challenges/{mission_id}")
async def challenge_detail(mission_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    return await get_challenge_detail(session, mission_id)


@router.get("/v1/mission-challenges/{mission_id}/capabilities")
async def challenge_capabilities(
    mission_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    mission = await get_challenge_detail(session, mission_id)
    mission_row = await session.get(Mission, mission_id)
    assert mission_row is not None
    return {
        "mission_id": mission_id,
        "challenge_state": mission["state"],
        "capabilities": capability_manifest(),
        "generic_next_allowed_actions": await next_allowed_actions(
            session, mission=mission_row, agent_id=None
        ),
    }


@router.post("/v1/mission-challenges/{mission_id}/join", status_code=201)
async def post_join_challenge(
    mission_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("mission_challenge_join", device.agent_id)
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    try:
        participant = await join_challenge(
            session,
            mission_id=mission_id,
            agent_id=device.agent_id,
            agent_version_id=agent.current_version_id,
            trace_id=getattr(request.state, "trace_id", None),
        )
    except ProvenanceMismatch:
        await session.commit()
        raise
    mission = await get_challenge_detail(session, mission_id)
    await session.commit()
    await _fan_out(
        mission_id,
        mission.get("hosting_space_id"),
        {
            "event": "challenge_joined",
            "mission_id": mission_id,
            "agent_id": device.agent_id,
            "roles": participant.roles,
        },
    )
    return {"mission_id": mission_id, "agent_id": participant.agent_id, "roles": participant.roles}


@router.post("/v1/mission-challenges/{mission_id}/submission-drafts", status_code=201)
async def post_submission_draft(
    mission_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("mission_challenge_submit", device.agent_id)
    body = await request.json()
    validate_challenge_draft(body)
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    result = await create_submission_draft(
        session,
        mission_id=mission_id,
        agent_id=device.agent_id,
        agent_version_id=agent.current_version_id,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    mission = await get_challenge_detail(session, mission_id)
    await session.commit()
    await _fan_out(
        mission_id,
        mission.get("hosting_space_id"),
        {
            "event": "challenge_submission_draft_created",
            "mission_id": mission_id,
            "submission_id": result["submission"]["submission_id"],
            "agent_id": device.agent_id,
            "receipt_id": result["receipt"]["receipt_id"] if result.get("receipt") else None,
        },
    )
    return result


@router.post("/v1/mission-challenges/{mission_id}/submissions", status_code=201)
async def post_submission(
    mission_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("mission_challenge_submit", device.agent_id)
    body = await request.json()
    validate_challenge_submission(body)
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    submission = await submit_solution(
        session,
        mission_id=mission_id,
        agent_id=device.agent_id,
        agent_version_id=agent.current_version_id,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    mission = await get_challenge_detail(session, mission_id)
    await session.commit()
    await _fan_out(
        mission_id,
        mission.get("hosting_space_id"),
        {
            "event": "challenge_solution_submitted",
            "mission_id": mission_id,
            "submission_id": submission.submission_id,
            "agent_id": device.agent_id,
        },
    )
    return submission_view(submission)


@router.post("/v1/mission-challenges/submissions/{submission_id}/evidence")
async def post_submission_evidence(
    submission_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("mission_challenge_submit", device.agent_id)
    body = await request.json()
    validate_challenge_evidence_attachment(body)
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    result = await attach_submission_evidence(
        session,
        submission_id=submission_id,
        agent_id=device.agent_id,
        agent_version_id=agent.current_version_id,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _fan_out(
        result["submission"]["mission_id"],
        None,
        {
            "event": "challenge_submission_evidence_attached",
            "mission_id": result["submission"]["mission_id"],
            "submission_id": submission_id,
            "agent_id": device.agent_id,
            "receipt_id": result["receipt"]["receipt_id"],
        },
    )
    return result


@router.post("/v1/mission-challenges/submissions/{submission_id}/finalize")
async def post_submission_finalize(
    submission_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("mission_challenge_submit", device.agent_id)
    body = await request.json()
    validate_challenge_finalize(body)
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    result = await finalize_submission_draft(
        session,
        submission_id=submission_id,
        agent_id=device.agent_id,
        agent_version_id=agent.current_version_id,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    mission = await get_challenge_detail(session, result["submission"]["mission_id"])
    await session.commit()
    await _fan_out(
        result["submission"]["mission_id"],
        mission.get("hosting_space_id"),
        {
            "event": "challenge_submission_finalized",
            "mission_id": result["submission"]["mission_id"],
            "submission_id": submission_id,
            "agent_id": device.agent_id,
            "receipt_id": result["receipt"]["receipt_id"] if result.get("receipt") else None,
        },
    )
    return result


@router.post("/v1/mission-challenges/submissions/{submission_id}/withdraw")
async def post_submission_withdrawal(
    submission_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("mission_challenge_submit", device.agent_id)
    body = await request.json()
    validate_challenge_withdrawal(body)
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    result = await withdraw_submission(
        session,
        submission_id=submission_id,
        agent_id=device.agent_id,
        agent_version_id=agent.current_version_id,
        reason=body["reason"],
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _fan_out(
        result["submission"]["mission_id"],
        None,
        {
            "event": "challenge_submission_withdrawn",
            "mission_id": result["submission"]["mission_id"],
            "submission_id": submission_id,
            "agent_id": device.agent_id,
            "receipt_id": result["receipt"]["receipt_id"],
        },
    )
    return result


@router.post("/v1/mission-challenges/submissions/{submission_id}/votes")
async def post_submission_vote(
    submission_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("mission_challenge_vote", device.agent_id)
    body = await request.json()
    validate_challenge_vote(body)
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    result = await vote_solution(
        session,
        submission_id=submission_id,
        voter_agent_id=device.agent_id,
        voter_agent_version_id=agent.current_version_id,
        verdict=body["verdict"],
        rationale=body["public_rationale"],
        idempotency_key=body["idempotency_key"],
        review_evidence_ids=body.get("review_evidence_ids") or [],
        conflict_of_interest_declaration=body["conflict_of_interest_declaration"],
        trace_id=getattr(request.state, "trace_id", None),
    )
    mission = result["mission"]
    await session.commit()
    await _fan_out(
        mission["mission_id"],
        mission.get("hosting_space_id"),
        {
            "event": "challenge_vote_cast",
            "mission_id": mission["mission_id"],
            "submission_id": submission_id,
            "verdict": body["verdict"],
            "resolved": body["verdict"] == "resolved",
            "challenge_resolved": result["resolved"],
        },
    )
    return result


@router.post("/v1/mission-challenges/submissions/{submission_id}/abstentions")
async def post_submission_abstention(
    submission_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("mission_challenge_vote", device.agent_id)
    body = await request.json()
    validate_challenge_abstention(body)
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    result = await vote_solution(
        session,
        submission_id=submission_id,
        voter_agent_id=device.agent_id,
        voter_agent_version_id=agent.current_version_id,
        verdict="abstain",
        rationale=body["reason"],
        idempotency_key=body["idempotency_key"],
        review_evidence_ids=[],
        conflict_of_interest_declaration="abstained",
        trace_id=getattr(request.state, "trace_id", None),
    )
    mission = result["mission"]
    await session.commit()
    await _fan_out(
        mission["mission_id"],
        mission.get("hosting_space_id"),
        {
            "event": "challenge_vote_abstained",
            "mission_id": mission["mission_id"],
            "submission_id": submission_id,
            "challenge_resolved": result["resolved"],
        },
    )
    return result
