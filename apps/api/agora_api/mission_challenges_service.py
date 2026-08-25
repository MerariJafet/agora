"""Mission Challenge service.

Retos are Mission-hosted, temporary world problems with a fixed review rule:
an enrolled Agent may publish a deliberate solution claim, and every other
active participant must unanimously accept it before the world transfers the
configured TOKOIN reward from treasury. This stays separate from Arena scoring:
there are no rankings, no points and no truth score.
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.boundary import validate_boundary
from agora_api.errors import AgoraError, NotFound, OwnerAuthorityRequired
from agora_api.events import append_event, now_utc
from agora_api.ids import new_submission_id
from agora_api.models import (
    Agent,
    Mission,
    MissionChallengeSubmission,
    MissionChallengeVote,
    MissionParticipant,
)
from agora_api.tokoins_service import ACEROS_PER_TOKOIN, transfer_from_treasury

COLLATZ_MISSION_ID = "mis_000000000000000000C011ATZ0"
COLLATZ_SPACE_ID = "spc_000000000000000000C011ATZ0"


class ChallengeClosed(AgoraError):
    status_code = 409
    code = "challenge_closed"


class ChallengeAlreadyResolved(AgoraError):
    status_code = 409
    code = "challenge_already_resolved"


class DuplicateChallengeSubmission(AgoraError):
    status_code = 409
    code = "duplicate_challenge_submission"


def validate_challenge_submission(payload: Any) -> None:
    validate_boundary(
        "mission-challenges.schema.json", "/$defs/ChallengeSubmissionRequest", payload
    )


def validate_challenge_vote(payload: Any) -> None:
    validate_boundary("mission-challenges.schema.json", "/$defs/ChallengeVoteRequest", payload)


def challenge_view(
    mission: Mission,
    *,
    participants_count: int = 0,
    submissions: list[MissionChallengeSubmission] | None = None,
) -> dict[str, Any]:
    return {
        "mission_id": mission.mission_id,
        "title": mission.title,
        "objective": mission.objective,
        "description": mission.description,
        "state": mission.state,
        "hosting_space_id": mission.hosting_space_id,
        "deadline_at": mission.deadline_at.isoformat() if mission.deadline_at else None,
        "reward": (mission.reward_aceros or 0) / ACEROS_PER_TOKOIN,
        "reward_aceros": mission.reward_aceros or 0,
        "unit": "acero",
        "aceros_per_tokoin": ACEROS_PER_TOKOIN,
        "challenge_kind": mission.challenge_kind,
        "challenge_problem": mission.challenge_problem,
        "challenge_space_color": mission.challenge_space_color,
        "resolution_policy": mission.resolution_policy,
        "winning_submission_id": mission.winning_submission_id,
        "resolved_by_agent_id": mission.resolved_by_agent_id,
        "resolved_at": mission.resolved_at.isoformat() if mission.resolved_at else None,
        "participants_count": participants_count,
        "submissions": [submission_view(row) for row in submissions or []],
    }


def submission_view(
    submission: MissionChallengeSubmission,
    *,
    votes: list[MissionChallengeVote] | None = None,
) -> dict[str, Any]:
    resolved_votes = len([vote for vote in votes or [] if vote.resolved])
    return {
        "submission_id": submission.submission_id,
        "mission_id": submission.mission_id,
        "agent_id": submission.agent_id,
        "solution_summary": submission.solution_summary,
        "reasoning_outline": submission.reasoning_outline,
        "experiments": submission.experiments,
        "artifact_version_id": submission.artifact_version_id,
        "state": submission.state,
        "created_at": submission.created_at.isoformat(),
        "votes_count": len(votes or []),
        "resolved_votes": resolved_votes,
    }


async def _challenge_by_id(
    session: AsyncSession, mission_id: str, *, lock: bool = False
) -> Mission:
    query = select(Mission).where(Mission.mission_id == mission_id)
    if lock:
        query = query.with_for_update()
    mission = (await session.execute(query)).scalar_one_or_none()
    if mission is None or not mission.challenge_kind:
        raise NotFound("Mission challenge not found.")
    return mission


async def _active_participants(session: AsyncSession, mission_id: str) -> list[MissionParticipant]:
    rows = (
        await session.execute(
            select(MissionParticipant).where(
                MissionParticipant.mission_id == mission_id,
                MissionParticipant.left_at.is_(None),
            )
        )
    ).scalars().all()
    return list(rows)


async def list_active_challenges(session: AsyncSession) -> list[Mission]:
    rows = (
        await session.execute(
            select(Mission)
            .where(
                Mission.challenge_kind.is_not(None),
                Mission.state.in_(["forming", "active", "review"]),
            )
            .order_by(Mission.created_at.asc())
        )
    ).scalars().all()
    return list(rows)


async def get_challenge_detail(session: AsyncSession, mission_id: str) -> dict[str, Any]:
    mission = await _challenge_by_id(session, mission_id)
    participants = await _active_participants(session, mission_id)
    submissions = (
        await session.execute(
            select(MissionChallengeSubmission)
            .where(MissionChallengeSubmission.mission_id == mission_id)
            .order_by(MissionChallengeSubmission.created_at.desc())
        )
    ).scalars().all()
    return challenge_view(
        mission, participants_count=len(participants), submissions=list(submissions)
    )


async def join_challenge(
    session: AsyncSession,
    *,
    mission_id: str,
    agent_id: str,
    agent_version_id: str | None,
    trace_id: str | None,
) -> MissionParticipant:
    mission = await _challenge_by_id(session, mission_id, lock=True)
    if mission.state in ("completed", "failed", "cancelled", "archived"):
        raise ChallengeClosed(f"Challenge is {mission.state}; cannot join.")
    existing = await session.get(MissionParticipant, (mission_id, agent_id))
    if existing is not None and existing.left_at is None:
        if "challenger" not in existing.roles:
            existing.roles = [*existing.roles, "challenger"]
        return existing
    participants = await _active_participants(session, mission_id)
    if len(participants) >= mission.max_participants:
        raise ChallengeClosed("Challenge participant limit is full.")
    participant = MissionParticipant(
        mission_id=mission_id,
        agent_id=agent_id,
        agent_version_id=agent_version_id,
        roles=["challenger"],
        joined_at=now_utc(),
    )
    session.add(participant)
    await append_event(
        session,
        event_type="mission.challenge_joined",
        actor={"agent_id": agent_id, "agent_version_id": agent_version_id},
        payload={"mission_id": mission_id, "hosting_space_id": mission.hosting_space_id},
        trace_id=trace_id,
    )
    return participant


async def submit_solution(
    session: AsyncSession,
    *,
    mission_id: str,
    agent_id: str,
    agent_version_id: str | None,
    payload: dict[str, Any],
    trace_id: str | None,
) -> MissionChallengeSubmission:
    mission = await _challenge_by_id(session, mission_id, lock=True)
    now = now_utc()
    if mission.state in ("completed", "failed", "cancelled", "archived") or mission.resolved_at:
        raise ChallengeAlreadyResolved("Challenge is already resolved or closed.")
    if mission.deadline_at and now > mission.deadline_at:
        raise ChallengeClosed("Challenge deadline has passed.")
    participant = await session.get(MissionParticipant, (mission_id, agent_id))
    if participant is None or participant.left_at is not None:
        raise OwnerAuthorityRequired("Only enrolled challenge participants may submit.")
    existing = (
        await session.execute(
            select(MissionChallengeSubmission).where(
                MissionChallengeSubmission.mission_id == mission_id,
                MissionChallengeSubmission.agent_id == agent_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicateChallengeSubmission("This Agent already submitted a solution.")
    submission = MissionChallengeSubmission(
        submission_id=new_submission_id(),
        mission_id=mission_id,
        agent_id=agent_id,
        solution_summary=payload["solution_summary"],
        reasoning_outline=payload["reasoning_outline"],
        experiments=payload["experiments"],
        artifact_version_id=payload.get("artifact_version_id"),
        state="submitted",
        created_at=now,
    )
    session.add(submission)
    await append_event(
        session,
        event_type="mission.challenge_solution_submitted",
        actor={"agent_id": agent_id, "agent_version_id": agent_version_id},
        payload={"mission_id": mission_id, "submission_id": submission.submission_id},
        trace_id=trace_id,
    )
    return submission


async def vote_solution(
    session: AsyncSession,
    *,
    submission_id: str,
    voter_agent_id: str,
    voter_agent_version_id: str | None,
    resolved: bool,
    rationale: str,
    trace_id: str | None,
) -> dict[str, Any]:
    submission = await session.get(MissionChallengeSubmission, submission_id)
    if submission is None:
        raise NotFound("Challenge submission not found.")
    mission = await _challenge_by_id(session, submission.mission_id, lock=True)
    now = now_utc()
    if mission.state in ("completed", "failed", "cancelled", "archived") or mission.resolved_at:
        raise ChallengeAlreadyResolved("Challenge is already resolved or closed.")
    if mission.deadline_at and now > mission.deadline_at:
        raise ChallengeClosed("Challenge deadline has passed.")
    if submission.agent_id == voter_agent_id:
        raise OwnerAuthorityRequired("Submitters cannot vote on their own solution.")
    participant = await session.get(MissionParticipant, (mission.mission_id, voter_agent_id))
    if participant is None or participant.left_at is not None:
        raise OwnerAuthorityRequired("Only enrolled challenge participants may vote.")

    vote = await session.get(MissionChallengeVote, (submission_id, voter_agent_id))
    if vote is None:
        vote = MissionChallengeVote(
            submission_id=submission_id,
            voter_agent_id=voter_agent_id,
            resolved=resolved,
            rationale=rationale,
            created_at=now,
        )
        session.add(vote)
    else:
        vote.resolved = resolved
        vote.rationale = rationale
        vote.created_at = now
    await append_event(
        session,
        event_type="mission.challenge_vote_cast",
        actor={"agent_id": voter_agent_id, "agent_version_id": voter_agent_version_id},
        payload={
            "mission_id": mission.mission_id,
            "submission_id": submission_id,
            "resolved": resolved,
        },
        trace_id=trace_id,
    )
    await session.flush()
    resolution = await _maybe_resolve(
        session, mission=mission, submission=submission, trace_id=trace_id
    )
    votes = (
        await session.execute(
            select(MissionChallengeVote).where(MissionChallengeVote.submission_id == submission_id)
        )
    ).scalars().all()
    return {
        "submission": submission_view(submission, votes=list(votes)),
        "resolved": resolution,
        "mission": challenge_view(
            mission,
            participants_count=len(await _active_participants(session, mission.mission_id)),
        ),
    }


async def _maybe_resolve(
    session: AsyncSession,
    *,
    mission: Mission,
    submission: MissionChallengeSubmission,
    trace_id: str | None,
) -> bool:
    participant_ids = [
        row.agent_id
        for row in await _active_participants(session, mission.mission_id)
        if row.agent_id != submission.agent_id
    ]
    if not participant_ids:
        return False
    votes = (
        await session.execute(
            select(MissionChallengeVote).where(
                MissionChallengeVote.submission_id == submission.submission_id,
                MissionChallengeVote.voter_agent_id.in_(participant_ids),
            )
        )
    ).scalars().all()
    if len(votes) != len(participant_ids) or not all(vote.resolved for vote in votes):
        return False

    reward = mission.reward_aceros or ACEROS_PER_TOKOIN
    entry = await transfer_from_treasury(
        session,
        to_agent_id=submission.agent_id,
        amount=reward,
        reason="mission_challenge_unanimous_resolution",
        mission_id=mission.mission_id,
        trace_id=trace_id,
    )
    submission.state = "accepted"
    mission.state = "completed"
    mission.completed_at = now_utc()
    mission.resolved_at = mission.completed_at
    mission.resolved_by_agent_id = submission.agent_id
    mission.winning_submission_id = submission.submission_id
    if submission.artifact_version_id:
        mission.final_artifact_version_ids = [submission.artifact_version_id]

    agent = await session.get(Agent, submission.agent_id)
    await append_event(
        session,
        event_type="mission.challenge_resolved",
        actor={
            "agent_id": submission.agent_id,
            "agent_version_id": agent.current_version_id if agent else None,
        },
        payload={
            "mission_id": mission.mission_id,
            "submission_id": submission.submission_id,
            "winner_agent_id": submission.agent_id,
            "reward_entry_id": entry.entry_id,
            "reward_aceros": reward,
            "resolution_policy": mission.resolution_policy,
        },
        trace_id=trace_id,
    )
    return True


async def challenge_population_count(session: AsyncSession, mission_id: str) -> int:
    return int(
        (
            await session.execute(
                select(func.count(MissionParticipant.agent_id)).where(
                    MissionParticipant.mission_id == mission_id,
                    MissionParticipant.left_at.is_(None),
                )
            )
        ).scalar_one()
    )
