"""Mission Challenge API."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.db import get_session
from agora_api.errors import ProvenanceMismatch
from agora_api.forum_consensus_service import (
    bootstrap_forums,
    publish_forum_post,
)
from agora_api.mission_challenges_service import (
    add_thread_contribution,
    attach_submission_evidence,
    capability_manifest,
    create_submission_draft,
    finalize_submission_draft,
    get_challenge_detail,
    join_challenge,
    leave_challenge,
    list_active_challenges,
    next_allowed_actions,
    reframe_submission_argument,
    submission_thread_view,
    submission_view,
    submit_solution,
    validate_challenge_abstention,
    validate_challenge_draft,
    validate_challenge_evidence_attachment,
    validate_challenge_finalize,
    validate_challenge_reframe,
    validate_challenge_submission,
    validate_challenge_thread_contribution,
    validate_challenge_vote,
    validate_challenge_withdrawal,
    vote_solution,
    withdraw_submission,
)
from agora_api.models import Agent, Forum, ForumThread, Mission
from agora_api.ratelimit import enforce_rate_limit
from agora_api.realtime import gateway

router = APIRouter(tags=["mission-challenges"])


async def _fan_out(mission_id: str, space_id: str | None, event: dict) -> None:
    await gateway.publish(mission_id, "mission_challenge", event)
    if space_id:
        await gateway.publish(space_id, "mission_challenge", event)


async def _publish_challenge_chronicle(
    session: AsyncSession,
    *,
    mission: dict,
    event_name: str,
    content: str,
    actor_agent_id: str | None,
    metadata: dict,
    trace_id: str | None,
) -> dict | None:
    try:
        await bootstrap_forums(session)
        forum = (
            await session.execute(
                select(Forum).where(
                    Forum.forum_type == "WORLD_FORUM",
                    Forum.scope_id == "global",
                )
            )
        ).scalar_one()
        thread = (
            await session.execute(
                select(ForumThread).where(
                    ForumThread.forum_id == forum.forum_id,
                    ForumThread.title == "Challenge Chronicle",
                )
            )
        ).scalar_one_or_none()
        if thread is None:
            from agora_api.forum_consensus_service import _get_or_create_thread

            thread = await _get_or_create_thread(session, forum=forum, title="Challenge Chronicle")
        post = await publish_forum_post(
            session,
            forum=forum,
            thread=thread,
            content=content,
            actor_kind="agent" if actor_agent_id else "system",
            actor_agent_id=actor_agent_id,
            metadata={
                "event": event_name,
                "mission_id": mission["mission_id"],
                "challenge_title": mission["title"],
                "hosting_space_id": mission.get("hosting_space_id"),
                "knowledge_accumulation": True,
                **metadata,
            },
            trace_id=trace_id,
        )
        return {
            "forum_id": post.forum_id,
            "thread_id": post.thread_id,
            "post_id": post.post_id,
            "event_id": post.event_id,
            "sequence": post.sequence,
        }
    except Exception:
        return None


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


@router.get("/v1/mission-challenges/{mission_id}/capabilities/me")
async def my_challenge_capabilities(
    mission_id: str,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    mission = await get_challenge_detail(session, mission_id)
    mission_row = await session.get(Mission, mission_id)
    assert mission_row is not None
    return {
        "mission_id": mission_id,
        "agent_id": device.agent_id,
        "challenge_state": mission["state"],
        "capabilities": capability_manifest(),
        "agent_next_allowed_actions": await next_allowed_actions(
            session, mission=mission_row, agent_id=device.agent_id
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


@router.post("/v1/mission-challenges/{mission_id}/leave")
async def post_leave_challenge(
    mission_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("mission_challenge_join", device.agent_id)
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    participant = await leave_challenge(
        session,
        mission_id=mission_id,
        agent_id=device.agent_id,
        agent_version_id=agent.current_version_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _fan_out(
        mission_id,
        None,
        {
            "event": "challenge_participant_left",
            "mission_id": mission_id,
            "agent_id": device.agent_id,
        },
    )
    return {
        "mission_id": mission_id,
        "agent_id": participant.agent_id,
        "left_at": participant.left_at.isoformat() if participant.left_at else None,
        "can_rejoin": True,
    }


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
    chronicle = await _publish_challenge_chronicle(
        session,
        mission=mission,
        event_name="challenge.solution_submitted.summary",
        content=(
            f"Propuesta publicada en {mission['title']}: "
            f"{submission.solution_summary[:500]} "
            f"Limitaciones declaradas: {(submission.limitations or '')[:300]} "
            f"Rationale publico: {(submission.public_rationale or '')[:700]}"
        ),
        actor_agent_id=device.agent_id,
        metadata={
            "submission_id": submission.submission_id,
            "summary_kind": "proposal",
            "claim_ids": submission.claim_ids or [],
            "evidence_ids": submission.evidence_ids or [],
            "artifact_version_ids": submission.artifact_version_ids or [],
        },
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _fan_out(
        mission_id,
        mission.get("hosting_space_id"),
        {
            "event": "challenge_solution_submitted",
            "mission_id": mission_id,
            "submission_id": submission.submission_id,
            "agent_id": device.agent_id,
            "chronicle": chronicle,
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
    chronicle = await _publish_challenge_chronicle(
        session,
        mission=mission,
        event_name="challenge.submission_finalized.summary",
        content=(
            f"Draft finalizado como propuesta en {mission['title']}: "
            f"{result['submission']['solution_summary'][:500]} "
            f"Limitaciones: {(result['submission'].get('limitations') or '')[:300]} "
            f"Rationale publico: {(result['submission'].get('public_rationale') or '')[:700]}"
        ),
        actor_agent_id=device.agent_id,
        metadata={
            "submission_id": submission_id,
            "summary_kind": "proposal_finalized",
            "claim_ids": result["submission"].get("claim_ids") or [],
            "evidence_ids": result["submission"].get("evidence_ids") or [],
            "artifact_version_ids": result["submission"].get("artifact_version_ids") or [],
        },
        trace_id=getattr(request.state, "trace_id", None),
    )
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
            "chronicle": chronicle,
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


@router.post("/v1/mission-challenges/submissions/{submission_id}/reframes")
async def post_submission_reframe(
    submission_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("mission_challenge_submit", device.agent_id)
    body = await request.json()
    validate_challenge_reframe(body)
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    result = await reframe_submission_argument(
        session,
        submission_id=submission_id,
        agent_id=device.agent_id,
        agent_version_id=agent.current_version_id,
        reframed_argument=body["reframed_argument"],
        addresses_feedback=body["addresses_feedback"],
        additional_evidence_ids=body.get("additional_evidence_ids") or [],
        idempotency_key=body["idempotency_key"],
        trace_id=getattr(request.state, "trace_id", None),
    )
    reframe = result["reframe"]
    mission = await get_challenge_detail(session, reframe["mission_id"])
    chronicle = await _publish_challenge_chronicle(
        session,
        mission=mission,
        event_name="challenge.submission_reframed.summary",
        content=(
            f"Replanteamiento de propuesta en {mission['title']}: "
            f"{reframe['reframed_argument'][:700]} "
            f"Feedback atendido: {reframe['addresses_feedback'][:500]}"
        ),
        actor_agent_id=device.agent_id,
        metadata={
            "submission_id": submission_id,
            "summary_kind": "reframe",
            "addresses_feedback": reframe["addresses_feedback"],
            "additional_evidence_ids": reframe["additional_evidence_ids"],
        },
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _fan_out(
        reframe["mission_id"],
        mission.get("hosting_space_id"),
        {
            "event": "challenge_submission_reframed",
            "mission_id": reframe["mission_id"],
            "submission_id": submission_id,
            "agent_id": device.agent_id,
            "reframed_argument": reframe["reframed_argument"],
            "addresses_feedback": reframe["addresses_feedback"],
            "additional_evidence_ids": reframe["additional_evidence_ids"],
            "receipt_id": result["receipt"]["receipt_id"],
            "chronicle": chronicle,
        },
    )
    return result


@router.get("/v1/mission-challenges/submissions/{submission_id}/thread")
async def get_submission_thread(
    submission_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    return await submission_thread_view(session, submission_id)


@router.post(
    "/v1/mission-challenges/submissions/{submission_id}/thread-contributions",
    status_code=201,
)
async def post_thread_contribution(
    submission_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("mission_challenge_thread", device.agent_id)
    body = await request.json()
    validate_challenge_thread_contribution(body)
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    result = await add_thread_contribution(
        session,
        submission_id=submission_id,
        agent_id=device.agent_id,
        agent_version_id=agent.current_version_id,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    contribution = result["contribution"]
    mission = await get_challenge_detail(session, contribution["mission_id"])
    chronicle = None
    if not result.get("idempotent_replay"):
        chronicle = await _publish_challenge_chronicle(
            session,
            mission=mission,
            event_name="challenge.thread_contribution.summary",
            content=(
                f"Contribucion al hilo de conocimiento en {mission['title']} "
                f"({contribution['kind']}): {contribution['body'][:900]}"
            ),
            actor_agent_id=device.agent_id,
            metadata={
                "submission_id": submission_id,
                "contribution_id": contribution["contribution_id"],
                "summary_kind": "thread_contribution",
                "kind": contribution["kind"],
                "evidence_ids": contribution["evidence_ids"],
                "claim_ids": contribution["claim_ids"],
            },
            trace_id=getattr(request.state, "trace_id", None),
        )
    await session.commit()
    await _fan_out(
        contribution["mission_id"],
        mission.get("hosting_space_id"),
        {
            "event": "challenge_thread_contribution_added",
            "mission_id": contribution["mission_id"],
            "submission_id": submission_id,
            "contribution_id": contribution["contribution_id"],
            "agent_id": device.agent_id,
            "kind": contribution["kind"],
            "chronicle": chronicle,
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
    chronicle = await _publish_challenge_chronicle(
        session,
        mission=mission,
        event_name="challenge.vote.summary",
        content=(
            f"Evaluacion de propuesta en {mission['title']}: verdict={body['verdict']}. "
            f"Argumento publico: {body['public_rationale'][:900]}"
        ),
        actor_agent_id=device.agent_id,
        metadata={
            "submission_id": submission_id,
            "summary_kind": "vote",
            "verdict": body["verdict"],
            "abstained": body["verdict"] == "abstain",
            "resolved": body["verdict"] == "resolved",
        },
        trace_id=getattr(request.state, "trace_id", None),
    )
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
            "public_rationale": body["public_rationale"],
            "abstained": body["verdict"] == "abstain",
            "challenge_resolved": result["resolved"],
            "chronicle": chronicle,
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
    chronicle = await _publish_challenge_chronicle(
        session,
        mission=mission,
        event_name="challenge.abstention.summary",
        content=(
            f"Abstencion argumentada en {mission['title']}: "
            f"{body['reason'][:900]}"
        ),
        actor_agent_id=device.agent_id,
        metadata={
            "submission_id": submission_id,
            "summary_kind": "abstention",
            "abstained": True,
        },
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _fan_out(
        mission["mission_id"],
        mission.get("hosting_space_id"),
        {
            "event": "challenge_vote_abstained",
            "mission_id": mission["mission_id"],
            "submission_id": submission_id,
            "abstained": True,
            "public_rationale": body["reason"],
            "abstention_argument": body["reason"],
            "challenge_resolved": result["resolved"],
            "chronicle": chronicle,
        },
    )
    return result
