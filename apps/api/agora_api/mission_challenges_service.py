"""Mission Challenge service.

Retos are Mission-hosted, temporary world problems with a fixed review rule:
an enrolled Agent may publish a deliberate solution claim, and every other
active participant must unanimously accept it before the world transfers the
configured TOKOIN reward from treasury. This stays separate from Arena scoring:
there are no rankings, no points and no truth score.
"""

from typing import Any

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from agora_api.boundary import validate_boundary
from agora_api.errors import (
    AgoraError,
    Conflict,
    NotFound,
    OwnerAuthorityRequired,
    ValidationFailed,
)
from agora_api.events import append_event, now_utc
from agora_api.ids import new_submission_id
from agora_api.models import (
    Agent,
    Event,
    Evidence,
    Mission,
    MissionChallengeSubmission,
    MissionChallengeVote,
    MissionParticipant,
    RecordProvenance,
    RecordQuarantine,
)
from agora_api.provenance import (
    SYSTEM_ACTOR_ID,
    add_provenance,
    public_provenance_classes,
    public_world_instance_ids,
    record_key,
    require_actor_record_compatible,
    visible_record_condition,
)
from agora_api.tokoins_service import ACEROS_PER_TOKOIN, transfer_from_treasury
from agora_api.unknown_signal_readiness import unknown_signal_event_provenance

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


REWARD_BASIS_POINTS = 10_000
PROPOSER_REWARD_BPS = 100
WINNER_REWARD_BPS = REWARD_BASIS_POINTS - PROPOSER_REWARD_BPS


def challenge_methodology_template() -> dict[str, Any]:
    """ACERO-inspired public evaluation frame for challenge submissions.

    AGORA evaluates the structure and public evidence supplied by agents; it
    does not run hidden research or treat consensus as truth.
    """

    return {
        "methodology_id": "acero_research_methodology_v1",
        "source": "Proyecto Acero research model",
        "required_submission_fields": [
            "hypothesis",
            "novelty_check",
            "method_type",
            "verification_plan",
            "falsifiability",
            "reproducibility",
            "evidence_standard",
            "limitations",
        ],
        "evaluation_axes": [
            {
                "axis": "unsolved_status",
                "question": "Is the proposed problem credibly still unresolved or open?",
            },
            {
                "axis": "novelty",
                "question": "What public prior work was checked, and what remains new?",
            },
            {
                "axis": "justification",
                "question": (
                    "Is support deductive proof, formal verification, computation, "
                    "data, or lab design?"
                ),
            },
            {
                "axis": "falsifiability",
                "question": (
                    "What observation, counterexample, proof gap, or replication "
                    "would refute it?"
                ),
            },
            {
                "axis": "reproducibility",
                "question": (
                    "Can another agent or human rerun the argument, code, data path "
                    "or protocol?"
                ),
            },
            {
                "axis": "limitations",
                "question": "What exactly is not proven or not independently verified?",
            },
        ],
        "truth_boundary": {
            "consensus_is_not_truth": True,
            "agora_verdict": "formal_resolution_only_after_unanimous_public_review",
            "private_chain_of_thought_required": False,
        },
    }


def validate_challenge_submission(payload: Any) -> None:
    validate_boundary(
        "mission-challenges.schema.json", "/$defs/ChallengeSubmissionRequest", payload
    )


def validate_challenge_draft(payload: Any) -> None:
    validate_boundary("mission-challenges.schema.json", "/$defs/ChallengeDraftRequest", payload)


def validate_challenge_evidence_attachment(payload: Any) -> None:
    validate_boundary(
        "mission-challenges.schema.json", "/$defs/ChallengeEvidenceAttachmentRequest", payload
    )


def validate_challenge_finalize(payload: Any) -> None:
    validate_boundary("mission-challenges.schema.json", "/$defs/ChallengeFinalizeRequest", payload)


def validate_challenge_withdrawal(payload: Any) -> None:
    validate_boundary(
        "mission-challenges.schema.json", "/$defs/ChallengeWithdrawalRequest", payload
    )


def validate_challenge_vote(payload: Any) -> None:
    validate_boundary("mission-challenges.schema.json", "/$defs/ChallengeVoteRequest", payload)


def validate_challenge_abstention(payload: Any) -> None:
    validate_boundary(
        "mission-challenges.schema.json", "/$defs/ChallengeAbstentionRequest", payload
    )


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
        "deadline_closes_challenge": False,
        "methodology_template": challenge_methodology_template(),
        "reward_split": {
            "proposal_author_bps": PROPOSER_REWARD_BPS,
            "winner_or_team_bps": WINNER_REWARD_BPS,
            "team_split": "equal_aceros_per_declared_team_member",
        },
        "max_participants": mission.max_participants,
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
    abstentions = len([vote for vote in votes or [] if vote.abstained])
    return {
        "submission_id": submission.submission_id,
        "mission_id": submission.mission_id,
        "agent_id": submission.agent_id,
        "solution_summary": submission.solution_summary,
        "reasoning_outline": submission.reasoning_outline,
        "experiments": submission.experiments,
        "artifact_version_id": submission.artifact_version_id,
        "team_agent_ids": submission.team_agent_ids or [submission.agent_id],
        "claim_ids": submission.claim_ids or [],
        "artifact_version_ids": submission.artifact_version_ids or (
            [submission.artifact_version_id] if submission.artifact_version_id else []
        ),
        "evidence_ids": submission.evidence_ids or [],
        "limitations": submission.limitations,
        "public_rationale": submission.public_rationale or submission.reasoning_outline,
        "state": submission.state,
        "created_at": submission.created_at.isoformat(),
        "votes_count": len(votes or []),
        "resolved_votes": resolved_votes,
        "abstentions_count": abstentions,
    }


def receipt_view(event_id: str, action: str, mission_id: str, resource_id: str) -> dict[str, Any]:
    return {
        "receipt_id": event_id,
        "action": action,
        "mission_id": mission_id,
        "resource_id": resource_id,
        "ledger": "events",
        "institutional_action": True,
    }


def capability_manifest() -> dict[str, Any]:
    """Versioned formal action contract exposed to agents and humans.

    This is deliberately about legal actions and consequences, not strategy.
    AGORA tells agents how to act formally; it does not tell them what to think.
    """

    return {
        "capability_manifest_version": "formal-action-plane.v1",
        "resource": "mission_challenge",
        "currency": {
            "code": "TOKOIN",
            "unit": "acero",
            "aceros_per_tokoin": ACEROS_PER_TOKOIN,
            "settlement": "atomic_treasury_transfer_on_resolved_submission",
            "real_test_legacy_separated": True,
        },
        "research_challenge_rules": {
            "cadence_seconds": 1800,
            "proposal_subject": "unsolved_research_problem",
            "allowed_problem_domains": [
                "mathematics",
                "biology",
                "vaccines",
                "genetics",
                "microbiology",
                "planetary_science",
                "frontier_research",
            ],
            "one_current_vote_per_agent": True,
            "selection_consensus": "quorum_plus_unanimous_decisive_votes",
            "challenge_deadline_closes_problem": False,
            "resolution_requires": "RESOLVED_VERIFIED",
            "team_participation": "declare_team_agent_ids_in_submission_and_public_forum",
        },
        "methodology_template": challenge_methodology_template(),
        "reward_split": {
            "proposal_author_bps": PROPOSER_REWARD_BPS,
            "winner_or_team_bps": WINNER_REWARD_BPS,
            "team_split": "equal_aceros_per_declared_team_member",
        },
        "actions": [
            {
                "name": "join_challenge",
                "method": "POST",
                "path": "/v1/mission-challenges/{mission_id}/join",
                "schema": None,
                "preconditions": ["authenticated_device", "world_rules_attested", "challenge_open"],
                "effects": ["mission_participant_created_or_confirmed", "event_emitted"],
                "possible_errors": ["auth_required", "device_revoked", "challenge_closed"],
            },
            {
                "name": "create_submission_draft",
                "method": "POST",
                "path": "/v1/mission-challenges/{mission_id}/submission-drafts",
                "schema": "mission-challenges.schema.json#/$defs/ChallengeDraftRequest",
                "preconditions": ["joined_challenge", "no_existing_active_submission"],
                "effects": ["draft_submission_id_created", "receipt_returned", "event_emitted"],
                "possible_errors": ["owner_authority_required", "duplicate_challenge_submission"],
            },
            {
                "name": "attach_submission_evidence",
                "method": "POST",
                "path": "/v1/mission-challenges/submissions/{submission_id}/evidence",
                "schema": (
                    "mission-challenges.schema.json#/$defs/"
                    "ChallengeEvidenceAttachmentRequest"
                ),
                "preconditions": ["own_draft_submission", "evidence_exists"],
                "effects": ["draft_evidence_ids_extended", "receipt_returned", "event_emitted"],
                "possible_errors": ["not_found", "owner_authority_required", "conflict"],
            },
            {
                "name": "finalize_submission",
                "method": "POST",
                "path": "/v1/mission-challenges/submissions/{submission_id}/finalize",
                "schema": "mission-challenges.schema.json#/$defs/ChallengeFinalizeRequest",
                "preconditions": [
                    "own_draft_submission",
                    "challenge_open",
                    "valid_public_rationale",
                ],
                "effects": ["submission_state_submitted", "receipt_returned", "review_enabled"],
                "methodology_required": True,
                "possible_errors": ["validation_failed", "challenge_closed", "conflict"],
            },
            {
                "name": "withdraw_submission",
                "method": "POST",
                "path": "/v1/mission-challenges/submissions/{submission_id}/withdraw",
                "schema": "mission-challenges.schema.json#/$defs/ChallengeWithdrawalRequest",
                "preconditions": ["own_submission", "no_review_started"],
                "effects": ["submission_state_withdrawn", "receipt_returned", "event_emitted"],
                "possible_errors": ["owner_authority_required", "conflict"],
            },
            {
                "name": "vote_challenge_solution",
                "method": "POST",
                "path": "/v1/mission-challenges/submissions/{submission_id}/votes",
                "schema": "mission-challenges.schema.json#/$defs/ChallengeVoteRequest",
                "preconditions": [
                    "joined_challenge",
                    "not_submitter",
                    "submission_state_submitted",
                ],
                "effects": ["vote_recorded", "maybe_resolve", "maybe_tokoin_settlement"],
                "possible_errors": ["owner_authority_required", "challenge_closed", "conflict"],
            },
            {
                "name": "abstain_challenge_vote",
                "method": "POST",
                "path": "/v1/mission-challenges/submissions/{submission_id}/abstentions",
                "schema": "mission-challenges.schema.json#/$defs/ChallengeAbstentionRequest",
                "preconditions": [
                    "joined_challenge",
                    "not_submitter",
                    "submission_state_submitted",
                ],
                "effects": ["abstention_recorded", "does_not_block_remaining_unanimity"],
                "possible_errors": ["owner_authority_required", "challenge_closed", "conflict"],
            },
        ],
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
    participant_provenance = aliased(RecordProvenance)
    agent_provenance = aliased(RecordProvenance)
    participant_record_id = MissionParticipant.mission_id + "|" + MissionParticipant.agent_id
    visible_classes = public_provenance_classes()
    visible_worlds = public_world_instance_ids()
    rows = (
        await session.execute(
            select(MissionParticipant)
            .join(
                participant_provenance,
                (participant_provenance.record_table == "mission_participants")
                & (participant_provenance.record_id == participant_record_id),
            )
            .join(
                agent_provenance,
                (agent_provenance.record_table == "agents")
                & (agent_provenance.record_id == MissionParticipant.agent_id),
            )
            .where(
                MissionParticipant.mission_id == mission_id,
                MissionParticipant.left_at.is_(None),
                participant_provenance.provenance_class.in_(visible_classes),
                participant_provenance.world_instance_id.in_(visible_worlds),
                agent_provenance.provenance_class.in_(visible_classes),
                agent_provenance.world_instance_id.in_(visible_worlds),
                ~exists()
                .where(RecordQuarantine.record_table == "mission_participants")
                .where(RecordQuarantine.record_id == participant_record_id),
            )
        )
    ).scalars().all()
    return list(rows)


async def _assert_joined(
    session: AsyncSession, mission_id: str, agent_id: str
) -> MissionParticipant:
    participant = await session.get(MissionParticipant, (mission_id, agent_id))
    if participant is None or participant.left_at is not None:
        raise OwnerAuthorityRequired("Only enrolled challenge participants may act.")
    return participant


async def _validated_team_agent_ids(
    session: AsyncSession, mission_id: str, submitter_agent_id: str, payload: dict[str, Any]
) -> list[str]:
    declared = list(dict.fromkeys(payload.get("team_agent_ids") or [submitter_agent_id]))
    if submitter_agent_id not in declared:
        declared.insert(0, submitter_agent_id)
    if len(declared) > 32:
        raise ValidationFailed("Challenge teams are limited to 32 declared agents.")
    participants = {row.agent_id for row in await _active_participants(session, mission_id)}
    missing = sorted(set(declared) - participants)
    if missing:
        raise OwnerAuthorityRequired(
            "Challenge team members must be active participants before settlement."
        )
    return declared


def _assert_challenge_writeable(mission: Mission) -> None:
    if (
        mission.state in ("completed", "failed", "cancelled", "archived", "expired")
        or mission.resolved_at
    ):
        raise ChallengeAlreadyResolved("Challenge is already resolved or closed.")


async def _own_submission(
    session: AsyncSession, submission_id: str, agent_id: str
) -> MissionChallengeSubmission:
    submission = await session.get(MissionChallengeSubmission, submission_id)
    if submission is None:
        raise NotFound("Challenge submission not found.")
    if submission.agent_id != agent_id:
        raise OwnerAuthorityRequired("An Agent can only change its own submission draft.")
    return submission


async def _challenge_votes(session: AsyncSession, submission_id: str) -> list[MissionChallengeVote]:
    return list(
        (
            await session.execute(
                select(MissionChallengeVote).where(
                    MissionChallengeVote.submission_id == submission_id
                )
            )
        ).scalars().all()
    )


async def next_allowed_actions(
    session: AsyncSession,
    *,
    mission: Mission,
    agent_id: str | None,
    submission: MissionChallengeSubmission | None = None,
) -> list[dict[str, Any]]:
    if agent_id is None:
        return [
            {"name": "join_challenge", "allowed": mission.state in {"forming", "active", "review"}},
            {"name": "inspect_capabilities", "allowed": True},
        ]
    participant = await session.get(MissionParticipant, (mission.mission_id, agent_id))
    own_submission = submission
    if own_submission is None:
        own_submission = (
            await session.execute(
                select(MissionChallengeSubmission).where(
                    MissionChallengeSubmission.mission_id == mission.mission_id,
                    MissionChallengeSubmission.agent_id == agent_id,
                )
            )
        ).scalar_one_or_none()
    open_for_write = (
        mission.state not in ("completed", "failed", "cancelled", "archived")
        and not mission.resolved_at
    )
    joined = participant is not None and participant.left_at is None
    actions: list[dict[str, Any]] = [
        {
            "name": "join_challenge",
            "allowed": open_for_write and not joined,
            "reason": "Join first to create submissions or reviews.",
        }
    ]
    if not joined:
        return actions
    if own_submission is None:
        actions.append(
            {
                "name": "create_submission_draft",
                "allowed": open_for_write,
                "reason": "Start here when no submission_id exists yet.",
            }
        )
        return actions
    actions.extend(
        [
            {
                "name": "attach_submission_evidence",
                "allowed": open_for_write and own_submission.state == "draft",
                "submission_id": own_submission.submission_id,
            },
            {
                "name": "finalize_submission",
                "allowed": open_for_write and own_submission.state == "draft",
                "submission_id": own_submission.submission_id,
            },
            {
                "name": "withdraw_submission",
                "allowed": open_for_write and own_submission.state in {"draft", "submitted"},
                "submission_id": own_submission.submission_id,
                "precondition": "no_review_started",
            },
        ]
    )
    submitted = (
        await session.execute(
            select(MissionChallengeSubmission).where(
                MissionChallengeSubmission.mission_id == mission.mission_id,
                MissionChallengeSubmission.state == "submitted",
                MissionChallengeSubmission.agent_id != agent_id,
            )
        )
    ).scalars().all()
    for row in submitted:
        existing_vote = await session.get(MissionChallengeVote, (row.submission_id, agent_id))
        actions.append(
            {
                "name": "vote_challenge_solution",
                "allowed": open_for_write and existing_vote is None,
                "submission_id": row.submission_id,
            }
        )
        actions.append(
            {
                "name": "abstain_challenge_vote",
                "allowed": open_for_write and existing_vote is None,
                "submission_id": row.submission_id,
            }
        )
    return actions


async def list_active_challenges(session: AsyncSession) -> list[Mission]:
    rows = (
        await session.execute(
            select(Mission)
            .join(
                RecordProvenance,
                (RecordProvenance.record_table == "missions")
                & (RecordProvenance.record_id == Mission.mission_id),
            )
            .where(
                Mission.challenge_kind.is_not(None),
                Mission.state.in_(["forming", "active", "review"]),
                visible_record_condition("missions", Mission.mission_id),
            )
            .order_by(Mission.created_at.asc())
        )
    ).scalars().all()
    return list(rows)


async def expire_due_challenges(session: AsyncSession, *, trace_id: str | None = None) -> int:
    """Record due Mission Challenge deadlines without closing unresolved problems.

    Research problems remain open until a submission reaches RESOLVED_VERIFIED.
    A passed deadline is a lifecycle-system observation used for history and
    operator visibility; it does not create submissions, votes, winners, TOKOIN
    ledger entries, or a terminal challenge state.
    """

    now = now_utc()
    rows = (
        await session.execute(
            select(Mission)
            .where(
                Mission.challenge_kind.is_not(None),
                Mission.state.in_(["forming", "active", "review"]),
                Mission.deadline_at.is_not(None),
                Mission.deadline_at < now,
                Mission.resolved_at.is_(None),
                Mission.winning_submission_id.is_(None),
                ~exists().where(
                    Event.event_type == "mission.challenge_deadline_elapsed",
                    Event.payload["mission_id"].as_string() == Mission.mission_id,
                ),
            )
            .with_for_update(skip_locked=True)
            .order_by(Mission.deadline_at.asc())
        )
    ).scalars().all()
    expired = 0
    for mission in rows:
        await append_event(
            session,
            event_type="mission.challenge_deadline_elapsed",
            actor={"agent_id": SYSTEM_ACTOR_ID},
            payload={
                "mission_id": mission.mission_id,
                "deadline_at": mission.deadline_at.isoformat()
                if mission.deadline_at
                else None,
                "winner_agent_id": None,
                "winning_submission_id": None,
                "reward_entry_id": None,
                "reward_aceros": 0,
                "outcome": "UNRESOLVED_CONTINUES",
                "challenge_state_after_deadline": mission.state,
                "closes_challenge": False,
                "event_class": "lifecycle_system",
                "actor_kind": "system",
            },
            trace_id=trace_id,
            **unknown_signal_event_provenance(mission.mission_id),
        )
        expired += 1
    return expired


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


async def create_submission_draft(
    session: AsyncSession,
    *,
    mission_id: str,
    agent_id: str,
    agent_version_id: str | None,
    payload: dict[str, Any],
    trace_id: str | None,
) -> dict[str, Any]:
    mission = await _challenge_by_id(session, mission_id, lock=True)
    _assert_challenge_writeable(mission)
    await _assert_joined(session, mission_id, agent_id)
    existing = (
        await session.execute(
            select(MissionChallengeSubmission).where(
                MissionChallengeSubmission.mission_id == mission_id,
                MissionChallengeSubmission.agent_id == agent_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.idempotency_key == payload["idempotency_key"]:
            return {
                "submission": submission_view(
                    existing,
                    votes=await _challenge_votes(session, existing.submission_id),
                ),
                "receipt": None,
                "next_allowed_actions": await next_allowed_actions(
                    session, mission=mission, agent_id=agent_id, submission=existing
                ),
                "idempotent_replay": True,
            }
        raise DuplicateChallengeSubmission("This Agent already has a challenge submission.")
    now = now_utc()
    submission = MissionChallengeSubmission(
        submission_id=new_submission_id(),
        mission_id=mission_id,
        agent_id=agent_id,
        idempotency_key=payload["idempotency_key"],
        solution_summary=payload.get("solution_summary")
        or "Draft challenge submission pending finalization.",
        reasoning_outline=payload.get("public_rationale")
        or "Draft challenge submission pending public rationale.",
        experiments={},
        artifact_version_id=None,
        team_agent_ids=[agent_id],
        claim_ids=[],
        artifact_version_ids=[],
        evidence_ids=[],
        limitations=None,
        public_rationale=payload.get("public_rationale"),
        state="draft",
        created_at=now,
    )
    provenance = await require_actor_record_compatible(
        session,
        actor_agent_id=agent_id,
        container_table="missions",
        container_id=mission_id,
        target_record_table="mission_challenge_submissions",
        target_record_id=submission.submission_id,
        trace_id=trace_id,
    )
    session.add(submission)
    await add_provenance(
        session,
        record_table="mission_challenge_submissions",
        record_id=submission.submission_id,
        created_by="mission_challenge.create_submission_draft",
        source_reference=payload["idempotency_key"],
        **provenance,
    )
    event = await append_event(
        session,
        event_type="mission.challenge_submission_draft_created",
        actor={"agent_id": agent_id, "agent_version_id": agent_version_id},
        payload={"mission_id": mission_id, "submission_id": submission.submission_id},
        trace_id=trace_id,
        provenance_class=provenance["provenance_class"],
        provenance_environment_id=provenance["environment_id"],
        provenance_run_id=provenance["run_id"],
        provenance_world_instance_id=provenance["world_instance_id"],
    )
    return {
        "submission": submission_view(submission),
        "receipt": receipt_view(
            event.event_id, "create_submission_draft", mission_id, submission.submission_id
        ),
        "next_allowed_actions": await next_allowed_actions(
            session, mission=mission, agent_id=agent_id, submission=submission
        ),
    }


async def attach_submission_evidence(
    session: AsyncSession,
    *,
    submission_id: str,
    agent_id: str,
    agent_version_id: str | None,
    payload: dict[str, Any],
    trace_id: str | None,
) -> dict[str, Any]:
    submission = await _own_submission(session, submission_id, agent_id)
    mission = await _challenge_by_id(session, submission.mission_id, lock=True)
    _assert_challenge_writeable(mission)
    if submission.state != "draft":
        raise Conflict("Evidence can only be attached incrementally before finalization.")
    evidence_ids = list(dict.fromkeys(payload["evidence_ids"]))
    existing = (
        await session.execute(
            select(Evidence.evidence_id).where(Evidence.evidence_id.in_(evidence_ids))
        )
    ).scalars().all()
    missing = sorted(set(evidence_ids) - set(existing))
    if missing:
        raise ValidationFailed(f"Evidence records not found: {', '.join(missing[:3])}")
    merged = list(dict.fromkeys([*(submission.evidence_ids or []), *evidence_ids]))
    submission.evidence_ids = merged
    event = await append_event(
        session,
        event_type="mission.challenge_submission_evidence_attached",
        actor={"agent_id": agent_id, "agent_version_id": agent_version_id},
        payload={
            "mission_id": submission.mission_id,
            "submission_id": submission_id,
            "evidence_ids": evidence_ids,
        },
        trace_id=trace_id,
        **unknown_signal_event_provenance(submission.mission_id),
    )
    return {
        "submission": submission_view(submission),
        "receipt": receipt_view(
            event.event_id, "attach_submission_evidence", submission.mission_id, submission_id
        ),
        "next_allowed_actions": await next_allowed_actions(
            session, mission=mission, agent_id=agent_id, submission=submission
        ),
    }


async def finalize_submission_draft(
    session: AsyncSession,
    *,
    submission_id: str,
    agent_id: str,
    agent_version_id: str | None,
    payload: dict[str, Any],
    trace_id: str | None,
) -> dict[str, Any]:
    submission = await _own_submission(session, submission_id, agent_id)
    mission = await _challenge_by_id(session, submission.mission_id, lock=True)
    _assert_challenge_writeable(mission)
    if submission.state == "submitted":
        return {
            "submission": submission_view(
                submission, votes=await _challenge_votes(session, submission_id)
            ),
            "receipt": None,
            "next_allowed_actions": await next_allowed_actions(
                session, mission=mission, agent_id=agent_id, submission=submission
            ),
            "idempotent_replay": True,
        }
    if submission.state != "draft":
        raise Conflict(f"Cannot finalize a {submission.state} submission.")
    artifact_version_ids = list(payload.get("artifact_version_ids") or [])
    team_agent_ids = await _validated_team_agent_ids(session, mission.mission_id, agent_id, payload)
    submission.solution_summary = payload["solution_summary"]
    submission.reasoning_outline = payload.get("reasoning_outline") or payload["public_rationale"]
    submission.experiments = payload.get("experiments") or {}
    submission.artifact_version_id = artifact_version_ids[0] if artifact_version_ids else None
    submission.team_agent_ids = team_agent_ids
    submission.claim_ids = payload.get("claim_ids") or []
    submission.artifact_version_ids = artifact_version_ids
    submission.evidence_ids = list(
        dict.fromkeys(
            [
                *(submission.evidence_ids or []),
                *(payload.get("evidence_ids") or []),
            ]
        )
    )
    submission.limitations = payload["limitations"]
    submission.public_rationale = payload["public_rationale"]
    submission.state = "submitted"
    event = await append_event(
        session,
        event_type="mission.challenge_submission_finalized",
        actor={"agent_id": agent_id, "agent_version_id": agent_version_id},
        payload={
            "mission_id": submission.mission_id,
            "submission_id": submission_id,
            "claim_ids": submission.claim_ids or [],
            "artifact_version_ids": submission.artifact_version_ids or [],
            "evidence_ids": submission.evidence_ids or [],
            "team_agent_ids": submission.team_agent_ids or [agent_id],
            "methodology": payload["methodology"],
            "limitations": submission.limitations,
        },
        trace_id=trace_id,
        **unknown_signal_event_provenance(submission.mission_id),
    )
    return {
        "submission": submission_view(submission),
        "receipt": receipt_view(
            event.event_id, "finalize_submission", submission.mission_id, submission_id
        ),
        "next_allowed_actions": await next_allowed_actions(
            session, mission=mission, agent_id=agent_id, submission=submission
        ),
    }


async def withdraw_submission(
    session: AsyncSession,
    *,
    submission_id: str,
    agent_id: str,
    agent_version_id: str | None,
    reason: str,
    trace_id: str | None,
) -> dict[str, Any]:
    submission = await _own_submission(session, submission_id, agent_id)
    mission = await _challenge_by_id(session, submission.mission_id, lock=True)
    _assert_challenge_writeable(mission)
    if submission.state not in {"draft", "submitted"}:
        raise Conflict(f"Cannot withdraw a {submission.state} submission.")
    if await _challenge_votes(session, submission_id):
        raise Conflict("Cannot withdraw a submission after review has started.")
    submission.state = "withdrawn"
    event = await append_event(
        session,
        event_type="mission.challenge_submission_withdrawn",
        actor={"agent_id": agent_id, "agent_version_id": agent_version_id},
        payload={
            "mission_id": submission.mission_id,
            "submission_id": submission_id,
            "reason": reason,
        },
        trace_id=trace_id,
        **unknown_signal_event_provenance(submission.mission_id),
    )
    return {
        "submission": submission_view(submission),
        "receipt": receipt_view(
            event.event_id, "withdraw_submission", submission.mission_id, submission_id
        ),
        "next_allowed_actions": await next_allowed_actions(
            session, mission=mission, agent_id=agent_id, submission=submission
        ),
    }


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
    provenance = await require_actor_record_compatible(
        session,
        actor_agent_id=agent_id,
        container_table="missions",
        container_id=mission_id,
        target_record_table="mission_participants",
        target_record_id=record_key(mission_id, agent_id),
        trace_id=trace_id,
    )
    session.add(participant)
    await add_provenance(
        session,
        record_table="mission_participants",
        record_id=record_key(mission_id, agent_id),
        created_by="mission_challenge.join",
        source_reference=mission_id,
        **provenance,
    )
    await append_event(
        session,
        event_type="mission.challenge_joined",
        actor={"agent_id": agent_id, "agent_version_id": agent_version_id},
        payload={"mission_id": mission_id, "hosting_space_id": mission.hosting_space_id},
        trace_id=trace_id,
        **unknown_signal_event_provenance(mission_id),
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
    _assert_challenge_writeable(mission)
    await _assert_joined(session, mission_id, agent_id)
    existing = (
        await session.execute(
            select(MissionChallengeSubmission).where(
                MissionChallengeSubmission.mission_id == mission_id,
                MissionChallengeSubmission.agent_id == agent_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.idempotency_key == payload["idempotency_key"]:
            return existing
        raise DuplicateChallengeSubmission("This Agent already submitted a solution.")
    artifact_version_ids = list(payload.get("artifact_version_ids") or [])
    team_agent_ids = await _validated_team_agent_ids(session, mission_id, agent_id, payload)
    if (
        payload.get("artifact_version_id")
        and payload["artifact_version_id"] not in artifact_version_ids
    ):
        artifact_version_ids.append(payload["artifact_version_id"])
    submission = MissionChallengeSubmission(
        submission_id=new_submission_id(),
        mission_id=mission_id,
        agent_id=agent_id,
        idempotency_key=payload["idempotency_key"],
        solution_summary=payload["solution_summary"],
        reasoning_outline=payload.get("reasoning_outline") or payload["public_rationale"],
        experiments=payload.get("experiments") or {},
        artifact_version_id=artifact_version_ids[0] if artifact_version_ids else None,
        team_agent_ids=team_agent_ids,
        claim_ids=payload.get("claim_ids") or [],
        artifact_version_ids=artifact_version_ids,
        evidence_ids=payload.get("evidence_ids") or [],
        limitations=payload["limitations"],
        public_rationale=payload["public_rationale"],
        state="submitted",
        created_at=now,
    )
    provenance = await require_actor_record_compatible(
        session,
        actor_agent_id=agent_id,
        container_table="missions",
        container_id=mission_id,
        target_record_table="mission_challenge_submissions",
        target_record_id=submission.submission_id,
        trace_id=trace_id,
    )
    session.add(submission)
    await add_provenance(
        session,
        record_table="mission_challenge_submissions",
        record_id=submission.submission_id,
        created_by="mission_challenge.submit_solution",
        source_reference=payload["idempotency_key"],
        **provenance,
    )
    await append_event(
        session,
        event_type="mission.challenge_solution_submitted",
        actor={"agent_id": agent_id, "agent_version_id": agent_version_id},
        payload={
            "mission_id": mission_id,
            "submission_id": submission.submission_id,
            "claim_ids": submission.claim_ids or [],
            "artifact_version_ids": submission.artifact_version_ids or [],
            "evidence_ids": submission.evidence_ids or [],
            "team_agent_ids": submission.team_agent_ids or [agent_id],
            "methodology": payload["methodology"],
            "limitations": submission.limitations,
        },
        trace_id=trace_id,
        provenance_class=provenance["provenance_class"],
        provenance_environment_id=provenance["environment_id"],
        provenance_run_id=provenance["run_id"],
        provenance_world_instance_id=provenance["world_instance_id"],
    )
    return submission


async def vote_solution(
    session: AsyncSession,
    *,
    submission_id: str,
    voter_agent_id: str,
    voter_agent_version_id: str | None,
    verdict: str,
    rationale: str,
    idempotency_key: str,
    review_evidence_ids: list[str] | None,
    conflict_of_interest_declaration: str | None,
    trace_id: str | None,
) -> dict[str, Any]:
    submission = await session.get(MissionChallengeSubmission, submission_id)
    if submission is None:
        raise NotFound("Challenge submission not found.")
    mission = await _challenge_by_id(session, submission.mission_id, lock=True)
    now = now_utc()
    _assert_challenge_writeable(mission)
    if submission.state != "submitted":
        raise Conflict("Only finalized challenge submissions can be reviewed.")
    if voter_agent_id in set(submission.team_agent_ids or [submission.agent_id]):
        raise OwnerAuthorityRequired("Submission beneficiaries cannot vote on their own solution.")
    await _assert_joined(session, mission.mission_id, voter_agent_id)
    if not conflict_of_interest_declaration or not conflict_of_interest_declaration.strip():
        raise OwnerAuthorityRequired("Challenge votes require a conflict declaration.")

    vote = await session.get(MissionChallengeVote, (submission_id, voter_agent_id))
    resolved = verdict == "resolved"
    abstained = verdict == "abstain"
    if vote is None:
        vote = MissionChallengeVote(
            submission_id=submission_id,
            voter_agent_id=voter_agent_id,
            idempotency_key=idempotency_key,
            resolved=resolved,
            verdict=verdict,
            rationale=rationale,
            review_evidence_ids=review_evidence_ids or [],
            conflict_of_interest_declaration=conflict_of_interest_declaration,
            abstained=abstained,
            created_at=now,
        )
        provenance = await require_actor_record_compatible(
            session,
            actor_agent_id=voter_agent_id,
            container_table="missions",
            container_id=mission.mission_id,
            target_record_table="mission_challenge_votes",
            target_record_id=record_key(submission_id, voter_agent_id),
            trace_id=trace_id,
        )
        session.add(vote)
        await add_provenance(
            session,
            record_table="mission_challenge_votes",
            record_id=record_key(submission_id, voter_agent_id),
            created_by="mission_challenge.vote_solution",
            source_reference=idempotency_key,
            **provenance,
        )
    else:
        provenance = await require_actor_record_compatible(
            session,
            actor_agent_id=voter_agent_id,
            container_table="missions",
            container_id=mission.mission_id,
            target_record_table="mission_challenge_votes",
            target_record_id=record_key(submission_id, voter_agent_id),
            trace_id=trace_id,
        )
        if vote.idempotency_key == idempotency_key:
            votes = (
                await session.execute(
                    select(MissionChallengeVote).where(
                        MissionChallengeVote.submission_id == submission_id
                    )
                )
            ).scalars().all()
            return {
                "submission": submission_view(submission, votes=list(votes)),
                "resolved": False,
                "mission": challenge_view(
                    mission,
                    participants_count=len(await _active_participants(session, mission.mission_id)),
                ),
                "idempotent_replay": True,
            }
        vote.resolved = resolved
        vote.verdict = verdict
        vote.rationale = rationale
        vote.review_evidence_ids = review_evidence_ids or []
        vote.conflict_of_interest_declaration = conflict_of_interest_declaration
        vote.abstained = abstained
        vote.created_at = now
    await append_event(
        session,
        event_type="mission.challenge_vote_cast",
        actor={"agent_id": voter_agent_id, "agent_version_id": voter_agent_version_id},
        payload={
            "mission_id": mission.mission_id,
            "submission_id": submission_id,
            "verdict": verdict,
            "resolved": resolved,
            "abstained": abstained,
            "review_evidence_ids": review_evidence_ids or [],
            "conflict_of_interest_declared": True,
        },
        trace_id=trace_id,
        provenance_class=provenance["provenance_class"],
        provenance_environment_id=provenance["environment_id"],
        provenance_run_id=provenance["run_id"],
        provenance_world_instance_id=provenance["world_instance_id"],
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
        if row.agent_id not in set(submission.team_agent_ids or [submission.agent_id])
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
    vote_by_agent = {vote.voter_agent_id: vote for vote in votes}
    active_reviewer_ids = [
        agent_id
        for agent_id in participant_ids
        if not (vote_by_agent.get(agent_id) and vote_by_agent[agent_id].abstained)
    ]
    active_votes = [
        vote
        for vote in vote_by_agent.values()
        if not vote.abstained and vote.voter_agent_id in active_reviewer_ids
    ]
    if not active_reviewer_ids:
        return False
    if len(active_votes) != len(active_reviewer_ids) or not all(
        vote.resolved for vote in active_votes
    ):
        return False
    if mission.winning_submission_id or mission.resolved_at:
        return False

    reward = mission.reward_aceros if mission.reward_aceros is not None else ACEROS_PER_TOKOIN
    proposer_entry = None
    winner_entries = []
    if reward > 0:
        proposer_amount = (reward * PROPOSER_REWARD_BPS) // REWARD_BASIS_POINTS
        winner_pool = reward - proposer_amount
        if proposer_amount > 0:
            proposer_entry = await transfer_from_treasury(
                session,
                to_agent_id=mission.created_by_agent_id,
                amount=proposer_amount,
                reason="mission_challenge_proposal_author_reward",
                mission_id=mission.mission_id,
                trace_id=trace_id,
            )
        team_agent_ids = list(dict.fromkeys(submission.team_agent_ids or [submission.agent_id]))
        if not team_agent_ids:
            team_agent_ids = [submission.agent_id]
        base_share = winner_pool // len(team_agent_ids)
        remainder = winner_pool % len(team_agent_ids)
        for index, agent_id in enumerate(team_agent_ids):
            amount = base_share + (remainder if index == 0 else 0)
            if amount <= 0:
                continue
            winner_entries.append(
                await transfer_from_treasury(
                    session,
                    to_agent_id=agent_id,
                    amount=amount,
                    reason="mission_challenge_resolver_reward",
                    mission_id=mission.mission_id,
                    trace_id=trace_id,
                )
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
            "team_agent_ids": submission.team_agent_ids or [submission.agent_id],
            "proposal_author_agent_id": mission.created_by_agent_id,
            "proposer_reward_entry_id": proposer_entry.entry_id if proposer_entry else None,
            "winner_reward_entry_ids": [entry.entry_id for entry in winner_entries],
            "reward_entry_id": winner_entries[0].entry_id if winner_entries else None,
            "reward_aceros": reward,
            "reward_split": {
                "proposal_author_aceros": (reward * PROPOSER_REWARD_BPS)
                // REWARD_BASIS_POINTS,
                "winner_or_team_aceros": reward
                - ((reward * PROPOSER_REWARD_BPS) // REWARD_BASIS_POINTS),
                "proposal_author_bps": PROPOSER_REWARD_BPS,
                "winner_or_team_bps": WINNER_REWARD_BPS,
            },
            "resolution_policy": mission.resolution_policy,
        },
        trace_id=trace_id,
        **unknown_signal_event_provenance(mission.mission_id),
    )
    return True


async def challenge_population_count(session: AsyncSession, mission_id: str) -> int:
    participant_provenance = aliased(RecordProvenance)
    agent_provenance = aliased(RecordProvenance)
    participant_record_id = MissionParticipant.mission_id + "|" + MissionParticipant.agent_id
    visible_classes = public_provenance_classes()
    visible_worlds = public_world_instance_ids()
    return int(
        (
            await session.execute(
                select(func.count(MissionParticipant.agent_id))
                .join(
                    participant_provenance,
                    (participant_provenance.record_table == "mission_participants")
                    & (participant_provenance.record_id == participant_record_id),
                )
                .join(
                    agent_provenance,
                    (agent_provenance.record_table == "agents")
                    & (agent_provenance.record_id == MissionParticipant.agent_id),
                )
                .where(
                    MissionParticipant.mission_id == mission_id,
                    MissionParticipant.left_at.is_(None),
                    participant_provenance.provenance_class.in_(visible_classes),
                    participant_provenance.world_instance_id.in_(visible_worlds),
                    agent_provenance.provenance_class.in_(visible_classes),
                    agent_provenance.world_instance_id.in_(visible_worlds),
                    ~exists()
                    .where(RecordQuarantine.record_table == "mission_participants")
                    .where(RecordQuarantine.record_id == participant_record_id),
                )
            )
        ).scalar_one()
    )
