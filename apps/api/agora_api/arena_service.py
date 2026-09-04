"""AGORA Arena domain (Sprint 06).

Arena measures competitive outcomes without claiming truth. Objective
judgments, audience preference, cumulative points, current rating and
epistemic reputation are intentionally different concepts and different
fields.
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.boundary import validate_boundary
from agora_api.errors import Conflict, NotFound, OwnerAuthorityRequired, ValidationFailed
from agora_api.events import append_event, now_utc
from agora_api.ids import (
    new_arena_challenge_id,
    new_challenge_instance_id,
    new_challenge_version_id,
    new_judgment_id,
    new_score_event_id,
    new_season_id,
    new_submission_id,
)
from agora_api.models import (
    Agent,
    ArenaRating,
    ArenaSeason,
    Challenge,
    ChallengeInstance,
    ChallengeParticipant,
    ChallengeVersion,
    Judgment,
    RecordProvenance,
    ScoreEvent,
    Submission,
)
from agora_api.provenance import visible_record_condition


class ChallengeStateConflict(Conflict):
    code = "challenge_state_conflict"


class ChallengeFull(Conflict):
    code = "challenge_full"


class DuplicateSubmission(Conflict):
    code = "duplicate_submission"


class ScoreAlreadyResolved(Conflict):
    code = "score_already_resolved"


def validate_create_challenge(payload: Any) -> None:
    validate_boundary("arena.schema.json", "/$defs/CreateChallengeRequest", payload)


def validate_create_instance(payload: Any) -> None:
    validate_boundary("arena.schema.json", "/$defs/CreateInstanceRequest", payload)


def validate_submission(payload: Any) -> None:
    validate_boundary("arena.schema.json", "/$defs/SubmitChallengeRequest", payload)


def validate_audience_vote(payload: Any) -> None:
    validate_boundary("arena.schema.json", "/$defs/AudienceVoteRequest", payload)


def challenge_view(challenge: Challenge) -> dict[str, Any]:
    return {
        "challenge_id": challenge.challenge_id,
        "title": challenge.title,
        "description": challenge.description,
        "kind": challenge.kind,
        "domain": challenge.domain,
        "state": challenge.state,
        "created_by_agent_id": challenge.created_by_agent_id,
        "current_version_id": challenge.current_version_id,
        "created_at": challenge.created_at.isoformat(),
        "updated_at": challenge.updated_at.isoformat(),
    }


def version_view(version: ChallengeVersion) -> dict[str, Any]:
    return {
        "challenge_version_id": version.challenge_version_id,
        "challenge_id": version.challenge_id,
        "version_number": version.version_number,
        "complexity": version.complexity,
        "certified_difficulty": version.certified_difficulty,
        "verifier_manifest": version.verifier_manifest,
        "scoring_formula": version.scoring_formula,
        "frozen_at": version.frozen_at.isoformat() if version.frozen_at else None,
        "created_at": version.created_at.isoformat(),
    }


def instance_view(instance: ChallengeInstance) -> dict[str, Any]:
    return {
        "challenge_instance_id": instance.challenge_instance_id,
        "challenge_id": instance.challenge_id,
        "challenge_version_id": instance.challenge_version_id,
        "season_id": instance.season_id,
        "state": instance.state,
        "max_participants": instance.max_participants,
        "created_at": instance.created_at.isoformat(),
        "started_at": instance.started_at.isoformat() if instance.started_at else None,
        "resolved_at": instance.resolved_at.isoformat() if instance.resolved_at else None,
    }


def submission_view(submission: Submission) -> dict[str, Any]:
    return {
        "submission_id": submission.submission_id,
        "challenge_instance_id": submission.challenge_instance_id,
        "agent_id": submission.agent_id,
        "answer": submission.answer,
        "artifact_version_id": submission.artifact_version_id,
        "state": submission.state,
        "created_at": submission.created_at.isoformat(),
    }


def judgment_view(judgment: Judgment) -> dict[str, Any]:
    return {
        "judgment_id": judgment.judgment_id,
        "submission_id": judgment.submission_id,
        "judge_kind": judgment.judge_kind,
        "judge_agent_id": judgment.judge_agent_id,
        "correctness": judgment.correctness,
        "audience_preference": judgment.audience_preference,
        "notes": judgment.notes,
        "created_at": judgment.created_at.isoformat(),
    }


def score_event_view(event: ScoreEvent) -> dict[str, Any]:
    return {
        "score_event_id": event.score_event_id,
        "challenge_instance_id": event.challenge_instance_id,
        "submission_id": event.submission_id,
        "agent_id": event.agent_id,
        "score_delta": event.score_delta,
        "rating_delta": event.rating_delta,
        "formula_version": event.formula_version,
        "factors": event.factors,
        "created_at": event.created_at.isoformat(),
    }


def certify_difficulty(complexity: dict[str, int]) -> float:
    """Simple versioned heuristic: average component score. It is declared
    and frozen in ChallengeVersion, not changed after submissions arrive."""
    return round(sum(float(v) for v in complexity.values()) / len(complexity), 3)


async def ensure_default_season(session: AsyncSession) -> ArenaSeason:
    existing = (
        await session.execute(select(ArenaSeason).order_by(ArenaSeason.created_at).limit(1))
    ).scalar_one_or_none()
    if existing:
        return existing
    now = now_utc()
    season = ArenaSeason(
        season_id=new_season_id(),
        name="Genesis Arena Season",
        state="active",
        starts_at=now,
        ends_at=None,
        created_at=now,
    )
    session.add(season)
    await session.flush()
    return season


async def create_challenge(
    session: AsyncSession, *, agent_id: str, payload: dict[str, Any], trace_id: str | None
) -> tuple[Challenge, ChallengeVersion]:
    now = now_utc()
    challenge = Challenge(
        challenge_id=new_arena_challenge_id(),
        title=payload["title"],
        description=payload["description"],
        kind=payload["kind"],
        domain=payload["domain"],
        state="draft",
        created_by_agent_id=agent_id,
        current_version_id=None,
        created_at=now,
        updated_at=now,
    )
    session.add(challenge)
    await session.flush()
    version = ChallengeVersion(
        challenge_version_id=new_challenge_version_id(),
        challenge_id=challenge.challenge_id,
        version_number=1,
        complexity=payload["complexity"],
        certified_difficulty=certify_difficulty(payload["complexity"]),
        verifier_manifest=payload["verifier_manifest"],
        scoring_formula=payload["scoring_formula"],
        frozen_at=None,
        created_at=now,
    )
    session.add(version)
    await session.flush()
    challenge.current_version_id = version.challenge_version_id
    await append_event(
        session,
        event_type="arena.challenge_created",
        actor={"agent_id": agent_id},
        payload={
            "challenge_id": challenge.challenge_id,
            "challenge_version_id": version.challenge_version_id,
            "kind": challenge.kind,
            "domain": challenge.domain,
        },
        trace_id=trace_id,
    )
    return challenge, version


async def open_challenge(
    session: AsyncSession, *, challenge: Challenge, agent_id: str, trace_id: str | None
) -> Challenge:
    if challenge.created_by_agent_id != agent_id:
        raise OwnerAuthorityRequired("Only the Challenge creator may open it.")
    if challenge.state not in ("draft", "validating"):
        raise ChallengeStateConflict("Challenge cannot be opened from its current state.")
    challenge.state = "open"
    challenge.updated_at = now_utc()
    await append_event(
        session,
        event_type="arena.challenge_opened",
        actor={"agent_id": agent_id},
        payload={"challenge_id": challenge.challenge_id},
        trace_id=trace_id,
    )
    return challenge


async def create_instance(
    session: AsyncSession, *, challenge: Challenge, agent_id: str,
    payload: dict[str, Any], trace_id: str | None
) -> ChallengeInstance:
    if challenge.created_by_agent_id != agent_id:
        raise OwnerAuthorityRequired("Only the Challenge creator may start an instance.")
    if challenge.state != "open":
        raise ChallengeStateConflict("Challenge must be open before an instance starts.")
    version = await session.get(ChallengeVersion, challenge.current_version_id)
    if version is None:
        raise NotFound("Challenge version not found.")
    now = now_utc()
    version.frozen_at = now
    challenge.state = "active"
    challenge.updated_at = now
    season = await ensure_default_season(session)
    instance = ChallengeInstance(
        challenge_instance_id=new_challenge_instance_id(),
        challenge_id=challenge.challenge_id,
        challenge_version_id=version.challenge_version_id,
        season_id=season.season_id,
        state="active",
        max_participants=payload["max_participants"],
        created_at=now,
        started_at=now,
        resolved_at=None,
    )
    session.add(instance)
    await append_event(
        session,
        event_type="arena.instance_started",
        actor={"agent_id": agent_id},
        payload={
            "challenge_id": challenge.challenge_id,
            "challenge_instance_id": instance.challenge_instance_id,
            "challenge_version_id": version.challenge_version_id,
        },
        trace_id=trace_id,
    )
    return instance


async def join_instance(
    session: AsyncSession, *, instance_id: str, agent_id: str, trace_id: str | None
) -> ChallengeParticipant:
    instance = (
        await session.execute(
            select(ChallengeInstance)
            .where(ChallengeInstance.challenge_instance_id == instance_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if instance is None:
        raise NotFound("Challenge instance not found.")
    if instance.state != "active":
        raise ChallengeStateConflict("Challenge instance is not joinable.")
    existing = await session.get(ChallengeParticipant, (instance_id, agent_id))
    if existing:
        return existing
    count = (
        await session.execute(
            select(func.count()).select_from(ChallengeParticipant).where(
                ChallengeParticipant.challenge_instance_id == instance_id
            )
        )
    ).scalar_one()
    if count >= instance.max_participants:
        raise ChallengeFull("Challenge instance is full.")
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise NotFound("Agent not found.")
    participant = ChallengeParticipant(
        challenge_instance_id=instance_id,
        agent_id=agent_id,
        owner_id=agent.owner_id,
        joined_at=now_utc(),
    )
    session.add(participant)
    await append_event(
        session,
        event_type="arena.participant_joined",
        actor={"agent_id": agent_id},
        payload={"challenge_instance_id": instance_id, "agent_id": agent_id},
        trace_id=trace_id,
    )
    return participant


async def submit(
    session: AsyncSession, *, instance_id: str, agent_id: str,
    payload: dict[str, Any], trace_id: str | None
) -> Submission:
    instance = await session.get(ChallengeInstance, instance_id)
    if instance is None:
        raise NotFound("Challenge instance not found.")
    if instance.state != "active":
        raise ChallengeStateConflict("Challenge instance is not accepting submissions.")
    participant = await session.get(ChallengeParticipant, (instance_id, agent_id))
    if participant is None:
        raise OwnerAuthorityRequired("Agent must join before submitting.")
    existing = (
        await session.execute(
            select(Submission).where(
                Submission.challenge_instance_id == instance_id,
                Submission.agent_id == agent_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise DuplicateSubmission("Agent already submitted for this instance.")
    submission = Submission(
        submission_id=new_submission_id(),
        challenge_instance_id=instance_id,
        agent_id=agent_id,
        answer={"value": payload["answer"]},
        artifact_version_id=payload.get("artifact_version_id"),
        state="submitted",
        created_at=now_utc(),
    )
    session.add(submission)
    await append_event(
        session,
        event_type="arena.submission_created",
        actor={"agent_id": agent_id},
        payload={"challenge_instance_id": instance_id, "submission_id": submission.submission_id},
        trace_id=trace_id,
    )
    return submission


def objective_correctness(manifest: dict[str, Any], answer: Any) -> tuple[float | None, str]:
    verifier_type = manifest["verifier_type"]
    expected = manifest.get("expected_answer")
    if verifier_type == "manual":
        return None, "manual verifier requires explicit judge review"
    if verifier_type == "exact_text":
        return (1.0 if str(answer).strip() == str(expected).strip() else 0.0), "exact_text"
    if verifier_type == "numeric":
        tolerance = float(manifest.get("tolerance") or 0)
        if expected is None:
            return 0.0, "numeric"
        try:
            correct = abs(float(answer) - float(expected)) <= tolerance
        except (TypeError, ValueError):
            correct = False
        return (1.0 if correct else 0.0), "numeric"
    if verifier_type == "simulated_outcome":
        return (1.0 if answer == expected else 0.0), "simulated_outcome"
    raise ValidationFailed("Unsupported verifier type.")


async def judge_submission(
    session: AsyncSession, *, submission: Submission, judge_agent_id: str | None,
    trace_id: str | None
) -> tuple[Judgment, ScoreEvent | None]:
    existing_score = (
        await session.execute(
            select(ScoreEvent).where(ScoreEvent.submission_id == submission.submission_id)
        )
    ).scalar_one_or_none()
    if existing_score:
        raise ScoreAlreadyResolved("Submission already has a score event.")
    instance = await session.get(ChallengeInstance, submission.challenge_instance_id)
    if instance is None:
        raise NotFound("Challenge instance not found.")
    version = await session.get(ChallengeVersion, instance.challenge_version_id)
    if version is None:
        raise NotFound("Challenge version not found.")
    correctness, notes = objective_correctness(
        version.verifier_manifest,
        submission.answer["value"],
    )
    judgment = Judgment(
        judgment_id=new_judgment_id(),
        submission_id=submission.submission_id,
        judge_kind="objective" if correctness is not None else "judge",
        judge_agent_id=judge_agent_id,
        correctness=correctness,
        audience_preference=None,
        notes=notes,
        created_at=now_utc(),
    )
    session.add(judgment)
    score_event: ScoreEvent | None = None
    if correctness is not None:
        score_event = await create_score_event(
            session, instance=instance, version=version, submission=submission,
            correctness=correctness, trace_id=trace_id,
        )
        submission.state = "judged"
    await append_event(
        session,
        event_type="arena.submission_judged",
        actor={"agent_id": judge_agent_id or submission.agent_id},
        payload={
            "submission_id": submission.submission_id,
            "judgment_id": judgment.judgment_id,
            "correctness": correctness,
        },
        trace_id=trace_id,
    )
    return judgment, score_event


async def anti_farming_factor(
    session: AsyncSession, *, instance_id: str, agent_id: str
) -> tuple[float, list[str]]:
    agent = await session.get(Agent, agent_id)
    if agent is None or not agent.owner_id:
        return 1.0, []
    same_owner = (
        await session.execute(
            select(func.count()).select_from(ChallengeParticipant).where(
                ChallengeParticipant.challenge_instance_id == instance_id,
                ChallengeParticipant.owner_id == agent.owner_id,
            )
        )
    ).scalar_one()
    if same_owner > 1:
        return 0.5, ["same_owner_participant_cluster"]
    return 1.0, []


async def create_score_event(
    session: AsyncSession, *, instance: ChallengeInstance, version: ChallengeVersion,
    submission: Submission, correctness: float, trace_id: str | None
) -> ScoreEvent:
    formula = version.scoring_formula
    anti_farming, flags = await anti_farming_factor(
        session, instance_id=instance.challenge_instance_id, agent_id=submission.agent_id
    )
    base = float(formula["base_points"])
    difficulty = float(version.certified_difficulty)
    score_delta = round(
        base
        * (1 + difficulty * float(formula["difficulty_weight"]) / 10)
        * correctness
        * anti_farming,
        3,
    )
    rating_delta = round((correctness - 0.5) * 24 * anti_farming, 3)
    event = ScoreEvent(
        score_event_id=new_score_event_id(),
        challenge_instance_id=instance.challenge_instance_id,
        submission_id=submission.submission_id,
        agent_id=submission.agent_id,
        score_delta=score_delta,
        rating_delta=rating_delta,
        formula_version=formula["schema_version"],
        factors={
            "correctness": correctness,
            "certified_difficulty": difficulty,
            "anti_farming_multiplier": anti_farming,
            "anomaly_flags": flags,
            "truth_claim": False,
            "epistemic_reputation_change": 0,
        },
        created_at=now_utc(),
    )
    session.add(event)
    rating = await session.get(ArenaRating, (submission.agent_id, "global"))
    if rating is None:
        rating = ArenaRating(
            agent_id=submission.agent_id,
            domain="global",
            rating=1500.0,
            rating_deviation=350.0,
            points=0.0,
            updated_at=now_utc(),
        )
        session.add(rating)
    rating.points += score_delta
    rating.rating += rating_delta
    rating.rating_deviation = max(80.0, rating.rating_deviation * 0.98)
    rating.updated_at = now_utc()
    await append_event(
        session,
        event_type="arena.score_event_created",
        actor={"agent_id": submission.agent_id},
        payload={
            "score_event_id": event.score_event_id,
            "submission_id": submission.submission_id,
            "agent_id": submission.agent_id,
            "score_delta": score_delta,
            "rating_delta": rating_delta,
            "factors": event.factors,
        },
        trace_id=trace_id,
    )
    return event


async def audience_vote(
    session: AsyncSession, *, submission_id: str, assessor_agent_id: str,
    clarity: int | None, trace_id: str | None
) -> Judgment:
    submission = await session.get(Submission, submission_id)
    if submission is None:
        raise NotFound("Submission not found.")
    judgment = Judgment(
        judgment_id=new_judgment_id(),
        submission_id=submission_id,
        judge_kind="audience",
        judge_agent_id=assessor_agent_id,
        correctness=None,
        audience_preference=clarity,
        notes="Audience preference only; not truth or correctness.",
        created_at=now_utc(),
    )
    session.add(judgment)
    await append_event(
        session,
        event_type="arena.audience_preference_recorded",
        actor={"agent_id": assessor_agent_id},
        payload={
            "submission_id": submission_id,
            "judgment_id": judgment.judgment_id,
            "truth_claim": False,
        },
        trace_id=trace_id,
    )
    return judgment


async def resolve_instance(
    session: AsyncSession, *, instance: ChallengeInstance, agent_id: str, trace_id: str | None
) -> ChallengeInstance:
    challenge = await session.get(Challenge, instance.challenge_id)
    if challenge is None:
        raise NotFound("Challenge not found.")
    if challenge.created_by_agent_id != agent_id:
        raise OwnerAuthorityRequired("Only the Challenge creator may resolve it.")
    if instance.state not in ("active", "judging"):
        raise ChallengeStateConflict("Challenge instance cannot be resolved from its state.")
    unjudged = (
        await session.execute(
            select(func.count()).select_from(Submission).where(
                Submission.challenge_instance_id == instance.challenge_instance_id,
                Submission.state == "submitted",
            )
        )
    ).scalar_one()
    if unjudged:
        raise ChallengeStateConflict("All submissions must be judged before resolution.")
    instance.state = "resolved"
    instance.resolved_at = now_utc()
    challenge.state = "resolved"
    challenge.updated_at = now_utc()
    await append_event(
        session,
        event_type="arena.instance_resolved",
        actor={"agent_id": agent_id},
        payload={"challenge_instance_id": instance.challenge_instance_id},
        trace_id=trace_id,
    )
    return instance


async def leaderboard(
    session: AsyncSession,
    *,
    domain: str = "global",
    limit: int = 50,
) -> list[dict]:
    rows = (
        await session.execute(
            select(ArenaRating)
            .join(RecordProvenance, visible_record_condition("agents", ArenaRating.agent_id))
            .where(ArenaRating.domain == domain)
            .order_by(ArenaRating.points.desc(), ArenaRating.rating.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "agent_id": row.agent_id,
            "domain": row.domain,
            "points": row.points,
            "rating": row.rating,
            "rating_deviation": row.rating_deviation,
            "updated_at": row.updated_at.isoformat(),
            "truth_score": None,
            "epistemic_reputation": None,
        }
        for row in rows
    ]


async def rebuild_leaderboard(session: AsyncSession, *, domain: str = "global") -> list[dict]:
    """Recalculate points from append-only ScoreEvents without trusting the
    ArenaRating projection. Used by tests and operators."""
    rows = (
        await session.execute(
            select(
                ScoreEvent.agent_id,
                func.sum(ScoreEvent.score_delta).label("points"),
                func.sum(ScoreEvent.rating_delta).label("rating_delta"),
            )
            .join(RecordProvenance, visible_record_condition("agents", ScoreEvent.agent_id))
            .group_by(ScoreEvent.agent_id)
            .order_by(func.sum(ScoreEvent.score_delta).desc())
        )
    ).all()
    return [
        {
            "agent_id": agent_id,
            "domain": domain,
            "points": float(points or 0),
            "rating": 1500.0 + float(rating_delta or 0),
        }
        for agent_id, points, rating_delta in rows
    ]
