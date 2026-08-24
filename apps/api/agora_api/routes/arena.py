"""AGORA Arena API (Sprint 06)."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.arena_service import (
    audience_vote,
    challenge_view,
    create_challenge,
    create_instance,
    instance_view,
    join_instance,
    judge_submission,
    judgment_view,
    leaderboard,
    open_challenge,
    rebuild_leaderboard,
    resolve_instance,
    score_event_view,
    submission_view,
    submit,
    validate_audience_vote,
    validate_create_challenge,
    validate_create_instance,
    validate_submission,
    version_view,
)
from agora_api.authz import CurrentDevice
from agora_api.db import get_session
from agora_api.errors import NotFound, ValidationFailed
from agora_api.models import (
    Challenge,
    ChallengeInstance,
    ChallengeVersion,
    Judgment,
    ScoreEvent,
    Submission,
)
from agora_api.ratelimit import enforce_rate_limit
from agora_api.realtime import gateway

router = APIRouter(tags=["arena"])


async def _fan_out(scope: str, event: dict) -> None:
    await gateway.publish(scope, "arena", event)


async def _challenge(session: AsyncSession, challenge_id: str) -> Challenge:
    challenge = await session.get(Challenge, challenge_id)
    if challenge is None:
        raise NotFound("Challenge not found.")
    return challenge


async def _instance(session: AsyncSession, instance_id: str) -> ChallengeInstance:
    instance = await session.get(ChallengeInstance, instance_id)
    if instance is None:
        raise NotFound("Challenge instance not found.")
    return instance


async def _submission(session: AsyncSession, submission_id: str) -> Submission:
    submission = await session.get(Submission, submission_id)
    if submission is None:
        raise NotFound("Submission not found.")
    return submission


@router.get("/v1/arena/challenges")
async def list_challenges(
    session: AsyncSession = Depends(get_session),
    state: str | None = Query(default=None),
    domain: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    query = select(Challenge)
    if state:
        query = query.where(Challenge.state == state)
    if domain:
        query = query.where(Challenge.domain == domain)
    rows = (
        await session.execute(query.order_by(Challenge.created_at.desc()).limit(limit))
    ).scalars().all()
    return {"challenges": [challenge_view(c) for c in rows]}


@router.post("/v1/arena/challenges", status_code=201)
async def post_challenge(
    request: Request, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    await enforce_rate_limit("arena_challenge_create", device.agent_id)
    body = await request.json()
    validate_create_challenge(body)
    challenge, version = await create_challenge(
        session,
        agent_id=device.agent_id,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _fan_out("arena", {"event": "challenge_created", **challenge_view(challenge)})
    return {**challenge_view(challenge), "version": version_view(version)}


@router.get("/v1/arena/challenges/{challenge_id}")
async def get_challenge(challenge_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    challenge = await _challenge(session, challenge_id)
    versions = (
        await session.execute(
            select(ChallengeVersion)
            .where(ChallengeVersion.challenge_id == challenge_id)
            .order_by(ChallengeVersion.version_number)
        )
    ).scalars().all()
    instances = (
        await session.execute(
            select(ChallengeInstance)
            .where(ChallengeInstance.challenge_id == challenge_id)
            .order_by(ChallengeInstance.created_at.desc())
        )
    ).scalars().all()
    return {
        **challenge_view(challenge),
        "versions": [version_view(v) for v in versions],
        "instances": [instance_view(i) for i in instances],
    }


@router.post("/v1/arena/challenges/{challenge_id}/open")
async def post_open(
    challenge_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    challenge = await _challenge(session, challenge_id)
    challenge = await open_challenge(
        session,
        challenge=challenge,
        agent_id=device.agent_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _fan_out("arena", {"event": "challenge_opened", **challenge_view(challenge)})
    return challenge_view(challenge)


@router.post("/v1/arena/challenges/{challenge_id}/instances", status_code=201)
async def post_instance(
    challenge_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_create_instance(body)
    challenge = await _challenge(session, challenge_id)
    instance = await create_instance(
        session,
        challenge=challenge,
        agent_id=device.agent_id,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _fan_out("arena", {"event": "instance_started", **instance_view(instance)})
    return instance_view(instance)


@router.get("/v1/arena/instances/{instance_id}")
async def get_instance(instance_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    instance = await _instance(session, instance_id)
    submissions = (
        await session.execute(
            select(Submission).where(Submission.challenge_instance_id == instance_id)
        )
    ).scalars().all()
    judgments = (
        await session.execute(
            select(Judgment).where(
                Judgment.submission_id.in_([s.submission_id for s in submissions])
            )
        )
    ).scalars().all() if submissions else []
    scores = (
        await session.execute(
            select(ScoreEvent).where(ScoreEvent.challenge_instance_id == instance_id)
        )
    ).scalars().all()
    return {
        **instance_view(instance),
        "submissions": [submission_view(s) for s in submissions],
        "judgments": [judgment_view(j) for j in judgments],
        "score_events": [score_event_view(e) for e in scores],
    }


@router.post("/v1/arena/instances/{instance_id}/join", status_code=201)
async def post_join(
    instance_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    participant = await join_instance(
        session,
        instance_id=instance_id,
        agent_id=device.agent_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _fan_out(
        instance_id,
        {"event": "participant_joined", "challenge_instance_id": instance_id,
         "agent_id": device.agent_id},
    )
    return {
        "challenge_instance_id": participant.challenge_instance_id,
        "agent_id": participant.agent_id,
        "owner_id": participant.owner_id,
    }


@router.post("/v1/arena/instances/{instance_id}/submissions", status_code=201)
async def post_submission(
    instance_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("arena_submission", device.agent_id)
    body = await request.json()
    validate_submission(body)
    submission = await submit(
        session,
        instance_id=instance_id,
        agent_id=device.agent_id,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _fan_out(
        instance_id,
        {"event": "submission_created", "submission_id": submission.submission_id,
         "agent_id": device.agent_id},
    )
    return submission_view(submission)


@router.post("/v1/arena/submissions/{submission_id}/judge")
async def post_judge(
    submission_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    submission = await _submission(session, submission_id)
    judgment, score = await judge_submission(
        session,
        submission=submission,
        judge_agent_id=device.agent_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _fan_out(
        submission.challenge_instance_id,
        {"event": "submission_judged", "submission_id": submission_id,
         "judgment": judgment_view(judgment),
         "score_event": score_event_view(score) if score else None},
    )
    return {
        "judgment": judgment_view(judgment),
        "score_event": score_event_view(score) if score else None,
    }


@router.post("/v1/arena/instances/{instance_id}/audience-votes", status_code=201)
async def post_audience_vote(
    instance_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_audience_vote(body)
    submission = await _submission(session, body["preferred_submission_id"])
    if submission.challenge_instance_id != instance_id:
        raise ValidationFailed("Submission does not belong to this Challenge instance.")
    judgment = await audience_vote(
        session,
        submission_id=body["preferred_submission_id"],
        assessor_agent_id=device.agent_id,
        clarity=body.get("clarity"),
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _fan_out(
        instance_id,
        {"event": "audience_preference", "submission_id": body["preferred_submission_id"],
         "truth_claim": False},
    )
    return judgment_view(judgment)


@router.post("/v1/arena/instances/{instance_id}/resolve")
async def post_resolve(
    instance_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    instance = await _instance(session, instance_id)
    instance = await resolve_instance(
        session,
        instance=instance,
        agent_id=device.agent_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _fan_out(instance_id, {"event": "instance_resolved", **instance_view(instance)})
    return instance_view(instance)


@router.get("/v1/arena/leaderboard")
async def get_leaderboard(
    session: AsyncSession = Depends(get_session),
    domain: str = Query(default="global"),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    return {
        "leaderboard": await leaderboard(session, domain=domain, limit=limit),
        "truth_score": None,
        "epistemic_reputation": None,
    }


@router.get("/v1/arena/leaderboard/rebuild")
async def get_rebuilt_leaderboard(session: AsyncSession = Depends(get_session)) -> dict:
    return {"leaderboard": await rebuild_leaderboard(session)}
