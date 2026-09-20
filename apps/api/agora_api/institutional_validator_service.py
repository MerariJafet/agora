"""Blind synthetic institutional-review pilot.

Pilot validators are authenticated Agents with an additional, explicit actor
record. Their reviews exercise AGORA's protocol but never satisfy human
validation, publication, or TOKOIN settlement gates.
"""

from __future__ import annotations

import base64
from copy import deepcopy
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.config import get_settings
from agora_api.errors import Conflict, NotFound, OwnerAuthorityRequired, ValidationFailed
from agora_api.events import append_event, now_utc
from agora_api.ids import (
    new_institutional_validator_id,
    new_validator_assignment_id,
    new_validator_owner_decision_id,
    new_validator_review_id,
    new_validator_review_proposal_id,
)
from agora_api.magna_knowledge_ledger import canonical_json_hash, create_edge, create_object
from agora_api.models import (
    Agent,
    ArtifactVersion,
    Device,
    Event,
    Evidence,
    Forum,
    ForumPost,
    ForumThread,
    InstitutionalValidator,
    MagnaKnowledgeEdge,
    MagnaKnowledgeObject,
    Mission,
    MissionChallengeSubmission,
    MissionChallengeThreadContribution,
    MissionChallengeVote,
    MissionParticipant,
    ResearchCandidateSnapshot,
    ResearchRewardCalculation,
    SpaceMessage,
    User,
    ValidatorAssignment,
    ValidatorOwnerDecision,
    ValidatorReview,
    ValidatorReviewProposal,
)
from agora_api.provenance import SYSTEM_ACTOR_ID

PILOT_TYPE = "INSTITUTIONAL_VALIDATOR_TEST"
PILOT_BADGE = "TEST INSTITUTIONAL VALIDATOR"
PILOT_DISCLAIMER = "Synthetic validator used for AGORA protocol testing."
PILOT_CAPABILITIES = [
    "inspect_research_package",
    "request_evidence",
    "independent_reproduction",
    "submit_blind_review",
    "request_revision",
    "approve_reject_or_abstain",
]
POSITIVE = {"APPROVED", "APPROVED_WITH_MINOR_CHANGES"}
FINAL_REPRODUCTION_STATUSES = {"REPRODUCED", "PARTIALLY_REPRODUCED"}


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _require_pilot_control_plane() -> None:
    settings = get_settings()
    if settings.is_production or not settings.institutional_validator_pilot_enabled:
        raise OwnerAuthorityRequired("Synthetic institutional-validator pilot is disabled.")


def validator_view(row: InstitutionalValidator) -> dict[str, Any]:
    return {
        "actor_type": "INSTITUTIONAL_VALIDATOR",
        "validator_id": row.validator_id,
        "actor_id": row.actor_id,
        "validator_type": row.validator_type,
        "display_name": row.display_name,
        "institution_name": row.institution_name,
        "institution_type": row.institution_type,
        "legal_entity_id": row.legal_entity_id,
        "domain": row.domain,
        "jurisdiction": row.jurisdiction,
        "institution_mode": row.institution_mode,
        "accreditation_status": row.accreditation_status,
        "public_label": row.public_label,
        "brain_provider": row.brain_provider,
        "review_role": row.review_role,
        "synthetic_or_human": row.synthetic_or_human,
        "world_instance_id": row.world_instance_id,
        "public_key": row.public_key,
        "capabilities": row.capabilities,
        "scientific_domains": row.scientific_domains,
        "review_history": row.review_history,
        "reputation_score": row.reputation_score,
        "active_status": row.active_status,
        "activation_state": "ACTIVE" if row.active_status else "PENDING",
        "badge": PILOT_BADGE,
        "disclaimer": row.disclaimer,
        "can_satisfy_human_validation": False,
        "can_release_tokoin": False,
        "created_at": row.created_at.isoformat(),
    }


def _assignment_view(
    row: ValidatorAssignment,
    validator: InstitutionalValidator,
    review: ValidatorReview | None,
    proposal: ValidatorReviewProposal | None,
    *,
    reveal_details: bool,
) -> dict[str, Any]:
    if proposal is not None:
        owner_gate_state = proposal.state
    elif row.revealed_at is not None:
        owner_gate_state = "LEGACY_COMPLETED_BEFORE_OWNER_GATE"
    else:
        owner_gate_state = "AGENT_ANALYSIS_PENDING"
    result: dict[str, Any] = {
        "assignment_id": row.assignment_id,
        "candidate_id": row.candidate_id,
        "validator": validator_view(validator),
        "state": row.state,
        "committed": row.committed_at is not None,
        "commitment_hash": row.commitment_hash if row.committed_at is not None else None,
        "revealed": row.revealed_at is not None,
        "assigned_at": row.assigned_at.isoformat(),
        "committed_at": row.committed_at.isoformat() if row.committed_at else None,
        "revealed_at": row.revealed_at.isoformat() if row.revealed_at else None,
        "owner_gate": {
            "required": True,
            "state": owner_gate_state,
            "proposal_hash": proposal.proposal_hash if proposal else None,
            "proposal_version": proposal.proposal_version if proposal else None,
            "proposal_details_public": False,
        },
    }
    if reveal_details and review is not None:
        result["review"] = {
            "review_id": review.review_id,
            "verdict": review.verdict,
            "confidence": review.confidence,
            "reproduction_status": review.reproduction_status,
            "dimensions": review.dimensions,
            "summary": review.summary,
            "methodology_findings": review.methodology_findings,
            "reproduction_findings": review.reproduction_findings,
            "evidence_findings": review.evidence_findings,
            "critical_issues": review.critical_issues,
            "minor_issues": review.minor_issues,
            "requested_changes": review.requested_changes,
            "executed_tests": review.executed_tests,
            "artifacts_reviewed": review.artifacts_reviewed,
            "review_hash": review.review_hash,
            "genealogy_node_id": review.genealogy_node_id,
            "created_at": review.created_at.isoformat(),
            "synthetic_test_review": True,
        }
    return result


def _validate_review_consistency(
    validator: InstitutionalValidator, payload: dict[str, Any]
) -> None:
    reproduction_status = payload["reproduction_status"]
    if payload["verdict"] in POSITIVE and reproduction_status in {
        "FAILED_TO_REPRODUCE",
        "NOT_REPRODUCIBLE_FROM_PROVIDED_ARTIFACTS",
        "NOT_REPRODUCED_DUE_TO_TOOL_LIMITATION",
    }:
        raise ValidationFailed("A positive verdict cannot claim failed or incomplete reproduction.")
    if (
        validator.review_role == "REPRODUCTION_METHODOLOGY"
        and reproduction_status == "NOT_APPLICABLE"
    ):
        raise ValidationFailed(
            "The reproduction/methodology track must report a reproduction outcome."
        )


async def register_pilot_validator(
    session: AsyncSession,
    *,
    device: Device,
    payload: dict[str, Any],
    trace_id: str | None,
) -> InstitutionalValidator:
    _require_pilot_control_plane()
    marker = payload["institution_name"].upper()
    if "SIMULADA" not in marker and "SYNTHETIC" not in marker:
        raise ValidationFailed(
            "Pilot institution_name must explicitly include SIMULADA or SYNTHETIC."
        )
    existing = (
        await session.execute(
            select(InstitutionalValidator).where(InstitutionalValidator.actor_id == device.agent_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        immutable = {
            "display_name": existing.display_name,
            "institution_name": existing.institution_name,
            "institution_type": existing.institution_type,
            "legal_entity_id": existing.legal_entity_id,
            "domain": existing.domain,
            "jurisdiction": existing.jurisdiction,
            "institution_mode": existing.institution_mode,
            "accreditation_status": existing.accreditation_status,
            "public_label": existing.public_label,
            "brain_provider": existing.brain_provider,
            "review_role": existing.review_role,
            "scientific_domains": existing.scientific_domains,
        }
        if immutable == {key: payload[key] for key in immutable}:
            return existing
        raise Conflict("Validator identity is immutable after registration.")
    agent = await session.get(Agent, device.agent_id)
    if agent is None:
        raise NotFound("Agent not found.")
    row = InstitutionalValidator(
        validator_id=new_institutional_validator_id(),
        actor_id=device.agent_id,
        validator_type=PILOT_TYPE,
        display_name=payload["display_name"],
        institution_name=payload["institution_name"],
        institution_type=payload["institution_type"],
        legal_entity_id=payload["legal_entity_id"],
        domain=payload["domain"].lower(),
        jurisdiction=payload["jurisdiction"],
        institution_mode=payload["institution_mode"],
        accreditation_status=payload["accreditation_status"],
        public_label=payload["public_label"],
        brain_provider=payload["brain_provider"],
        review_role=payload["review_role"],
        synthetic_or_human="synthetic",
        world_instance_id=get_settings().world_instance_id,
        public_key=device.public_key,
        capabilities=PILOT_CAPABILITIES,
        scientific_domains=payload["scientific_domains"],
        review_history={"completed": 0, "approved": 0, "adverse": 0, "reproductions": 0},
        reputation_score=0,
        active_status=False,
        disclaimer=PILOT_DISCLAIMER,
        representative_owner_id=agent.owner_id,
        created_at=now_utc(),
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise Conflict("Agent is already registered as a validator.") from exc
    await append_event(
        session,
        event_type="institution.validator.created",
        actor={"agent_id": device.agent_id},
        payload={
            "validator_id": row.validator_id,
            "validator_type": PILOT_TYPE,
            "synthetic": True,
            "active": False,
            "can_satisfy_human_validation": False,
        },
        trace_id=trace_id,
    )
    return row


async def activate_pilot_validator(
    session: AsyncSession,
    *,
    validator_id: str,
    verifier: User,
    verification_evidence_hash: str,
    trace_id: str | None,
) -> InstitutionalValidator:
    _require_pilot_control_plane()
    row = await session.get(InstitutionalValidator, validator_id, with_for_update=True)
    if row is None:
        raise NotFound("Institutional Validator not found.")
    if row.active_status:
        return row
    agent = await session.get(Agent, row.actor_id)
    if agent is None or agent.owner_id is None:
        raise OwnerAuthorityRequired("Validator Agent must have a representative Owner.")
    row.representative_owner_id = agent.owner_id
    if verifier.user_id == row.representative_owner_id:
        raise OwnerAuthorityRequired(
            "A validator representative cannot activate its own synthetic institution."
        )
    row.active_status = True
    row.verified_by_owner_id = verifier.user_id
    row.verification_evidence_hash = verification_evidence_hash
    row.activated_at = now_utc()
    await append_event(
        session,
        event_type="institution.validator.activated",
        actor={"agent_id": SYSTEM_ACTOR_ID},
        payload={
            "validator_id": row.validator_id,
            "verifier_owner_id": verifier.user_id,
            "verification_evidence_hash": verification_evidence_hash,
            "synthetic_test_only": True,
        },
        trace_id=trace_id,
    )
    return row


async def assign_pilot_validators(
    session: AsyncSession,
    *,
    candidate_id: str,
    validator_ids: list[str],
    decision_owner_id: str,
    trace_id: str | None,
) -> list[ValidatorAssignment]:
    _require_pilot_control_plane()
    candidate = await session.get(ResearchCandidateSnapshot, candidate_id, with_for_update=True)
    if candidate is None:
        raise NotFound("Research candidate not found.")
    if candidate.state != "INSTITUTIONAL_REVIEW_PENDING":
        raise Conflict(
            "Pilot review requires an immutable candidate awaiting institutional review."
        )
    validators = list(
        (
            await session.execute(
                select(InstitutionalValidator).where(
                    InstitutionalValidator.validator_id.in_(validator_ids),
                    InstitutionalValidator.active_status.is_(True),
                    InstitutionalValidator.validator_type == PILOT_TYPE,
                )
            )
        ).scalars()
    )
    if len(validators) != 2 or len({row.actor_id for row in validators}) != 2:
        raise ValidationFailed("Exactly two distinct active pilot validators are required.")
    providers = {row.brain_provider for row in validators}
    if providers not in ({"codex", "claude"}, {"python-scripted-test"}):
        raise ValidationFailed(
            "Pilot panel requires Codex/Claude or two explicitly Python scripted TEST reviewers."
        )
    if {row.review_role for row in validators} != {
        "REPRODUCTION_METHODOLOGY",
        "FALSIFICATION_EVIDENCE",
    }:
        raise ValidationFailed("Pilot panel requires reproduction and falsification roles.")
    submission = await session.get(MissionChallengeSubmission, candidate.submission_id)
    candidate_authors = {candidate.created_by_agent_id}
    if submission is not None:
        candidate_authors.add(submission.agent_id)
        candidate_authors.update(submission.team_agent_ids or [])
    genealogy_authors = set(
        (
            await session.execute(
                select(MagnaKnowledgeObject.author_agent_id).where(
                    MagnaKnowledgeObject.challenge_id == candidate.challenge_id
                )
            )
        ).scalars()
    )
    conflicted = {
        row.validator_id
        for row in validators
        if row.actor_id in candidate_authors or row.actor_id in genealogy_authors
    }
    if conflicted:
        raise Conflict(
            "A pilot validator contributed to this candidate and cannot review it: "
            + ", ".join(sorted(conflicted))
        )
    existing = list(
        (
            await session.execute(
                select(ValidatorAssignment).where(ValidatorAssignment.candidate_id == candidate_id)
            )
        ).scalars()
    )
    if existing:
        if {row.validator_id for row in existing} == set(validator_ids):
            return existing
        raise Conflict("Candidate already has a validator panel; use explicit reassignment.")
    now = now_utc()
    rows = [
        ValidatorAssignment(
            assignment_id=new_validator_assignment_id(),
            validator_id=validator.validator_id,
            candidate_id=candidate_id,
            decision_owner_id=decision_owner_id,
            state="ASSIGNED",
            assigned_at=now,
        )
        for validator in validators
    ]
    session.add_all(rows)
    await session.flush()
    for row in rows:
        await append_event(
            session,
            event_type="institution.validator.assigned",
            actor={"agent_id": SYSTEM_ACTOR_ID},
            payload={
                "candidate_id": candidate_id,
                "assignment_id": row.assignment_id,
                "validator_id": row.validator_id,
                "blind_review": True,
                "synthetic": True,
            },
            trace_id=trace_id,
        )
    return rows


async def _owned_assignment(
    session: AsyncSession, assignment_id: str, device: Device, *, lock: bool = False
) -> tuple[ValidatorAssignment, InstitutionalValidator, ResearchCandidateSnapshot]:
    statement = (
        select(ValidatorAssignment, InstitutionalValidator)
        .join(
            InstitutionalValidator,
            InstitutionalValidator.validator_id == ValidatorAssignment.validator_id,
        )
        .where(ValidatorAssignment.assignment_id == assignment_id)
    )
    if lock:
        statement = statement.with_for_update()
    result = (await session.execute(statement)).one_or_none()
    if result is None:
        raise NotFound("Validator assignment not found.")
    assignment, validator = result
    if validator.actor_id != device.agent_id:
        raise OwnerAuthorityRequired("Only the assigned validator may act on this review.")
    candidate = await session.get(ResearchCandidateSnapshot, assignment.candidate_id)
    assert candidate is not None
    return assignment, validator, candidate


async def assignment_package(
    session: AsyncSession, *, assignment_id: str, device: Device
) -> dict[str, Any]:
    """Return only immutable candidate material to the assigned validator."""
    _require_pilot_control_plane()
    assignment, validator, candidate = await _owned_assignment(
        session, assignment_id, device, lock=True
    )
    # Serialize first materialization. Every later read/proposal uses these
    # same bytes, even if conversations, votes or mission metadata change.
    if assignment.review_package is not None:
        return deepcopy(assignment.review_package)
    if assignment.state != "ASSIGNED":
        raise Conflict("Legacy review has no frozen package; create a new candidate review.")
    mission = await session.get(Mission, candidate.challenge_id)
    submission = await session.get(MissionChallengeSubmission, candidate.submission_id)
    solution = await session.get(MagnaKnowledgeObject, candidate.final_solution_object_id)
    assert mission is not None and submission is not None and solution is not None
    solution_payload = solution.payload if solution.visibility_lane == "OPEN" else None
    participant_rows = list(
        (
            await session.execute(
                select(MissionParticipant, Agent)
                .join(Agent, Agent.agent_id == MissionParticipant.agent_id)
                .where(MissionParticipant.mission_id == candidate.challenge_id)
                .order_by(MissionParticipant.joined_at, MissionParticipant.agent_id)
            )
        ).all()
    )
    vote_rows = list(
        (
            await session.execute(
                select(MissionChallengeVote, Agent)
                .join(Agent, Agent.agent_id == MissionChallengeVote.voter_agent_id)
                .where(MissionChallengeVote.submission_id == candidate.submission_id)
                .order_by(MissionChallengeVote.created_at, MissionChallengeVote.voter_agent_id)
            )
        ).all()
    )
    thread_rows = list(
        (
            await session.execute(
                select(MissionChallengeThreadContribution, Agent)
                .join(Agent, Agent.agent_id == MissionChallengeThreadContribution.agent_id)
                .where(MissionChallengeThreadContribution.mission_id == candidate.challenge_id)
                .order_by(
                    MissionChallengeThreadContribution.created_at,
                    MissionChallengeThreadContribution.contribution_id,
                )
                .limit(500)
            )
        ).all()
    )
    space_messages: list[SpaceMessage] = []
    if mission.hosting_space_id:
        space_messages = list(
            (
                await session.execute(
                    select(SpaceMessage)
                    .where(SpaceMessage.space_id == mission.hosting_space_id)
                    .order_by(SpaceMessage.created_at.desc(), SpaceMessage.message_id.desc())
                    .limit(200)
                )
            ).scalars()
        )
        space_messages.reverse()
    forum_ids = list(
        (
            await session.execute(
                select(Forum.forum_id).where(Forum.scope_id == candidate.challenge_id)
            )
        ).scalars()
    )
    forum_posts: list[tuple[ForumPost, ForumThread]] = []
    if forum_ids:
        forum_posts = list(
            (
                await session.execute(
                    select(ForumPost, ForumThread)
                    .join(ForumThread, ForumThread.thread_id == ForumPost.thread_id)
                    .where(ForumPost.forum_id.in_(forum_ids))
                    .order_by(ForumPost.sequence)
                    .limit(300)
                )
            )
            .tuples()
            .all()
        )
    knowledge_objects = list(
        (
            await session.execute(
                select(MagnaKnowledgeObject)
                .where(
                    MagnaKnowledgeObject.challenge_id == candidate.challenge_id,
                    MagnaKnowledgeObject.visibility_lane == "OPEN",
                )
                .order_by(MagnaKnowledgeObject.created_at, MagnaKnowledgeObject.object_id)
                .limit(500)
            )
        ).scalars()
    )
    object_ids = [row.object_id for row in knowledge_objects]
    knowledge_edges: list[MagnaKnowledgeEdge] = []
    if object_ids:
        knowledge_edges = list(
            (
                await session.execute(
                    select(MagnaKnowledgeEdge)
                    .where(
                        MagnaKnowledgeEdge.source_object_id.in_(object_ids),
                        MagnaKnowledgeEdge.target_object_id.in_(object_ids),
                        MagnaKnowledgeEdge.retracted_at.is_(None),
                    )
                    .order_by(MagnaKnowledgeEdge.created_at, MagnaKnowledgeEdge.edge_id)
                    .limit(800)
                )
            ).scalars()
        )
    artifact_ids = list(
        dict.fromkeys(
            [*(submission.artifact_version_ids or [])]
            + ([submission.artifact_version_id] if submission.artifact_version_id else [])
            + (
                [candidate.manuscript_artifact_version_id]
                if candidate.manuscript_artifact_version_id
                else []
            )
        )
    )
    artifacts: list[ArtifactVersion] = []
    if artifact_ids:
        artifacts = list(
            (
                await session.execute(
                    select(ArtifactVersion).where(
                        ArtifactVersion.artifact_version_id.in_(artifact_ids)
                    )
                )
            ).scalars()
        )
    evidence_ids = list(dict.fromkeys(submission.evidence_ids or []))
    evidence_rows: list[Evidence] = []
    if evidence_ids:
        evidence_rows = list(
            (await session.execute(select(Evidence).where(Evidence.evidence_id.in_(evidence_ids))))
            .scalars()
        )
    event_rows = list(
        (
            await session.execute(
                select(Event)
                .where(
                    ~Event.event_type.like("institution.%"),
                    or_(
                        Event.payload.contains({"candidate_id": candidate.candidate_id}),
                        Event.payload.contains({"challenge_id": candidate.challenge_id}),
                        Event.payload.contains({"mission_id": candidate.challenge_id}),
                        Event.payload.contains({"submission_id": candidate.submission_id}),
                    )
                )
                .order_by(Event.occurred_at, Event.event_id)
                .limit(500)
            )
        ).scalars()
    )
    reward = (
        await session.execute(
            select(ResearchRewardCalculation).where(
                ResearchRewardCalculation.candidate_id == candidate.candidate_id
            )
        )
    ).scalar_one_or_none()
    review_context: dict[str, Any] = {
        "participants": [
            {
                "agent_id": participant.agent_id,
                "name": agent.name,
                "roles": participant.roles,
                "joined_at": participant.joined_at.isoformat(),
                "left_at": participant.left_at.isoformat() if participant.left_at else None,
            }
            for participant, agent in participant_rows
        ],
        "candidate_votes": [
            {
                "voter_agent_id": vote.voter_agent_id,
                "voter_name": agent.name,
                "verdict": vote.verdict,
                "resolved": vote.resolved,
                "abstained": vote.abstained,
                "rationale": vote.rationale,
                "review_evidence_ids": vote.review_evidence_ids or [],
                "conflict_declaration": vote.conflict_of_interest_declaration,
                "created_at": vote.created_at.isoformat(),
            }
            for vote, agent in vote_rows
        ],
        "challenge_thread": [
            {
                "entry_id": row.contribution_id,
                "submission_id": row.submission_id,
                "agent_id": row.agent_id,
                "agent_name": agent.name,
                "kind": row.kind,
                "body": row.body,
                "evidence_ids": row.evidence_ids or [],
                "claim_ids": row.claim_ids or [],
                "created_at": row.created_at.isoformat(),
            }
            for row, agent in thread_rows
        ],
        "world_conversation": [
            {
                "message_id": row.message_id,
                "agent_id": row.agent_id,
                "content": row.content,
                "reply_to": row.reply_to,
                "created_at": row.created_at.isoformat(),
            }
            for row in space_messages
        ],
        "forum_conversation": [
            {
                "post_id": post.post_id,
                "thread_id": post.thread_id,
                "thread_title": thread.title,
                "actor_agent_id": post.actor_agent_id,
                "content": post.content,
                "content_hash": post.content_hash,
                "published_at": post.published_at.isoformat(),
            }
            for post, thread in forum_posts
        ],
        "audit_events": [
            {
                "event_id": row.event_id,
                "event_type": row.event_type,
                "actor": row.actor,
                "payload": row.payload,
                "occurred_at": row.occurred_at.isoformat(),
            }
            for row in event_rows
        ],
        "genealogy": {
            "nodes": [
                {
                    "object_id": row.object_id,
                    "object_type": row.object_type,
                    "author_agent_id": row.author_agent_id,
                    "content_hash": row.canonical_content_hash,
                    "state": row.state,
                    "summary": row.public_summary,
                }
                for row in knowledge_objects
            ],
            "edges": [
                {
                    "edge_id": row.edge_id,
                    "source": row.source_object_id,
                    "target": row.target_object_id,
                    "relation": row.relation_type,
                }
                for row in knowledge_edges
            ],
        },
        "artifacts": [
            {
                "artifact_version_id": row.artifact_version_id,
                "state": row.state,
                "content_hash": row.content_hash,
                "content_size": row.content_size,
                "media_type": row.media_type,
                "display_filename": row.display_filename,
                "provenance_hash": row.provenance_hash,
            }
            for row in artifacts
        ],
        "evidence": [
            {
                "evidence_id": row.evidence_id,
                "source_type": row.source_type,
                "provenance_level": row.provenance_level,
                "title": row.title,
                "content_hash": row.content_hash,
                "evidence_kind": row.evidence_kind,
                "certificate_hash": row.certificate_hash,
            }
            for row in evidence_rows
        ],
        "reward_context": (
            {
                "reward_id": reward.reward_id,
                "state": reward.state,
                "total_aceros": reward.total_aceros,
                "allocation": reward.allocation,
                "algorithm_version": reward.algorithm_version,
                "advisory_only_for_synthetic_validator": True,
            }
            if reward
            else {
                "reward_id": None,
                "state": "NOT_CALCULATED",
                "total_aceros": 0,
                "allocation": {},
                "advisory_only_for_synthetic_validator": True,
            }
        ),
        "coverage_limits": {
            "challenge_thread": 500,
            "world_conversation": 200,
            "forum_conversation": 300,
            "audit_events": 500,
            "genealogy_nodes": 500,
            "genealogy_edges": 800,
        },
        "private_service_logs_disclosed": False,
    }
    review_context["context_hash"] = canonical_json_hash(
        review_context, domain="agora.institutional.validator.context.v1"
    )
    package = {
        "assignment_id": assignment.assignment_id,
        "validator_id": validator.validator_id,
        "review_role": validator.review_role,
        "blind_review": True,
        "peer_review_data_disclosed": False,
        "candidate": {
            "candidate_id": candidate.candidate_id,
            "candidate_version": candidate.candidate_version,
            "content_hash": candidate.content_hash,
            "knowledge_root_hash": candidate.knowledge_root_hash,
            "protocol_version": candidate.protocol_version,
            "final_solution_object_id": candidate.final_solution_object_id,
            "manuscript_artifact_version_id": candidate.manuscript_artifact_version_id,
        },
        "challenge": {
            "challenge_id": mission.mission_id,
            "title": mission.title,
            "objective": mission.objective,
            "problem": mission.challenge_problem,
        },
        "submission": {
            "submission_id": submission.submission_id,
            "author_agent_id": submission.agent_id,
            "team_agent_ids": submission.team_agent_ids or [],
            "solution_summary": submission.solution_summary,
            "reasoning_outline": submission.reasoning_outline,
            "experiments": submission.experiments,
            "limitations": submission.limitations,
            "public_rationale": submission.public_rationale,
            "artifact_version_ids": submission.artifact_version_ids or [],
            "evidence_ids": submission.evidence_ids or [],
        },
        "final_solution": {
            "object_id": solution.object_id,
            "object_type": solution.object_type,
            "canonical_content_hash": solution.canonical_content_hash,
            "visibility_lane": solution.visibility_lane,
            "payload": solution_payload,
        },
        "review_context": review_context,
    }
    assignment.review_package = package
    await session.flush()
    return deepcopy(package)


async def declare_conflict(
    session: AsyncSession,
    *,
    assignment_id: str,
    device: Device,
    declaration: str,
    trace_id: str | None,
) -> ValidatorAssignment:
    _require_pilot_control_plane()
    assignment, validator, _ = await _owned_assignment(session, assignment_id, device, lock=True)
    if assignment.committed_at is not None:
        raise Conflict("Conflict must be declared before committing a review.")
    assignment.state = "CONFLICT_DECLARED"
    assignment.conflict_declaration = declaration
    await append_event(
        session,
        event_type="institution.validator.conflict_declared",
        actor={"agent_id": device.agent_id},
        payload={"assignment_id": assignment_id, "validator_id": validator.validator_id},
        trace_id=trace_id,
    )
    return assignment


def review_commitment(
    assignment: ValidatorAssignment,
    validator: InstitutionalValidator,
    candidate: ResearchCandidateSnapshot,
    payload: dict[str, Any],
) -> str:
    body = {
        "assignment_id": assignment.assignment_id,
        "validator_id": validator.validator_id,
        "candidate_id": candidate.candidate_id,
        "candidate_content_hash": candidate.content_hash,
        "candidate_version": candidate.candidate_version,
        "review": payload,
    }
    return canonical_json_hash(body, domain="agora.institutional.validator.review.v1")


def review_proposal_hash(
    assignment: ValidatorAssignment,
    validator: InstitutionalValidator,
    candidate: ResearchCandidateSnapshot,
    *,
    proposal_version: int,
    payload: dict[str, Any],
) -> str:
    body = {
        "assignment_id": assignment.assignment_id,
        "validator_id": validator.validator_id,
        "candidate_id": candidate.candidate_id,
        "candidate_content_hash": candidate.content_hash,
        "candidate_version": candidate.candidate_version,
        "proposal_version": proposal_version,
        **payload,
    }
    return canonical_json_hash(body, domain="agora.institutional.validator.proposal.v1")


async def _latest_proposal(
    session: AsyncSession, assignment_id: str, *, lock: bool = False
) -> ValidatorReviewProposal | None:
    statement = (
        select(ValidatorReviewProposal)
        .where(ValidatorReviewProposal.assignment_id == assignment_id)
        .order_by(ValidatorReviewProposal.proposal_version.desc())
        .limit(1)
    )
    if lock:
        statement = statement.with_for_update()
    return (await session.execute(statement)).scalar_one_or_none()


def _validate_proposal_consistency(
    validator: InstitutionalValidator,
    review: dict[str, Any],
    recommendation: dict[str, Any],
    tokoin_recommendation: dict[str, Any],
    *,
    expected_total_aceros: int,
) -> None:
    _validate_review_consistency(validator, review)
    expected_assessment = {
        "APPROVED": "PASS",
        "APPROVED_WITH_MINOR_CHANGES": "PASS_WITH_CONDITIONS",
        "REQUIRES_REVISION": "PASS_WITH_CONDITIONS",
        "REJECTED": "FAIL",
        "INSUFFICIENT_EVIDENCE": "INSUFFICIENT_EVIDENCE",
    }[review["verdict"]]
    if recommendation["assessment"] != expected_assessment:
        raise ValidationFailed("Owner recommendation must agree with the proposed verdict.")
    if expected_assessment == "PASS" and recommendation["blocking_issues"]:
        raise ValidationFailed("A PASS recommendation cannot contain blocking issues.")
    total = int(tokoin_recommendation["total_aceros"])
    if total != expected_total_aceros:
        raise ValidationFailed("TOKOIN recommendation must use the frozen provisional total.")
    if sum(int(row["amount_aceros"]) for row in tokoin_recommendation["allocations"]) != total:
        raise ValidationFailed("TOKOIN recommendation allocations must sum to total_aceros.")


def _proposal_view(
    proposal: ValidatorReviewProposal,
    assignment: ValidatorAssignment,
    validator: InstitutionalValidator,
    decision: ValidatorOwnerDecision | None,
) -> dict[str, Any]:
    return {
        "proposal_id": proposal.proposal_id,
        "proposal_version": proposal.proposal_version,
        "proposal_hash": proposal.proposal_hash,
        "state": proposal.state,
        "assignment_id": proposal.assignment_id,
        "assignment_state": assignment.state,
        "candidate_id": proposal.candidate_id,
        "validator": validator_view(validator),
        "review": proposal.review_payload,
        "recommendation": proposal.recommendation,
        "evidence_manifest": proposal.evidence_manifest,
        "tokoin_recommendation": proposal.tokoin_recommendation,
        "decision": (
            {
                "decision_id": decision.decision_id,
                "decision": decision.decision,
                "proposal_hash": decision.proposal_hash,
                "owner_notes": decision.owner_notes,
                "decision_hash": decision.decision_hash,
                "created_at": decision.created_at.isoformat(),
            }
            if decision
            else None
        ),
        "approved_for_commit": proposal.state == "OWNER_APPROVED",
        "synthetic_test_only": True,
        "human_validation_satisfied": False,
        "tokoin_settlement_eligible": False,
        "disclaimer": PILOT_DISCLAIMER,
        "created_at": proposal.created_at.isoformat(),
    }


async def submit_review_proposal(
    session: AsyncSession,
    *,
    assignment_id: str,
    device: Device,
    payload: dict[str, Any],
    trace_id: str | None,
) -> ValidatorReviewProposal:
    _require_pilot_control_plane()
    assignment, validator, candidate = await _owned_assignment(
        session, assignment_id, device, lock=True
    )
    if assignment.committed_at is not None:
        raise Conflict("A committed review cannot be replaced by an Owner proposal.")
    if assignment.state in {"CONFLICT_DECLARED", "OWNER_REJECTED"}:
        raise Conflict("This assignment cannot accept a review proposal.")
    package = await assignment_package(session, assignment_id=assignment_id, device=device)
    manifest = payload["evidence_manifest"]
    context = package["review_context"]
    if manifest["context_hash"] != context["context_hash"]:
        raise ValidationFailed("Evidence manifest does not match the frozen review context.")
    allowed_participants = {row["agent_id"] for row in context["participants"]}
    allowed_threads = {
        *[row["entry_id"] for row in context["challenge_thread"]],
        *[row["message_id"] for row in context["world_conversation"]],
        *[row["post_id"] for row in context["forum_conversation"]],
    }
    allowed_events = {row["event_id"] for row in context["audit_events"]}
    allowed_artifacts = {
        *[row["artifact_version_id"] for row in context["artifacts"]],
        *[row["evidence_id"] for row in context["evidence"]],
        package["final_solution"]["object_id"],
    }
    if not set(manifest["participant_ids"]) <= allowed_participants:
        raise ValidationFailed("Evidence manifest cites an unknown participant.")
    if not set(manifest["thread_entry_ids"]) <= allowed_threads:
        raise ValidationFailed("Evidence manifest cites an unknown conversation entry.")
    if not set(manifest["event_ids"]) <= allowed_events:
        raise ValidationFailed("Evidence manifest cites an unknown audit event.")
    if not set(manifest["artifact_ids"]) <= allowed_artifacts:
        raise ValidationFailed("Evidence manifest cites an unknown artifact or evidence item.")
    reward_total = int(context["reward_context"]["total_aceros"])
    _validate_proposal_consistency(
        validator,
        payload["review"],
        payload["recommendation"],
        payload["tokoin_recommendation"],
        expected_total_aceros=reward_total,
    )
    previous = await _latest_proposal(session, assignment_id, lock=True)
    if previous is not None and previous.state != "REVISION_REQUESTED":
        existing_hash = review_proposal_hash(
            assignment,
            validator,
            candidate,
            proposal_version=previous.proposal_version,
            payload=payload,
        )
        if previous.proposal_hash == existing_hash:
            return previous
        raise Conflict("Current proposal must be decided before a new version is submitted.")
    next_version = 1 if previous is None else previous.proposal_version + 1
    computed = review_proposal_hash(
        assignment,
        validator,
        candidate,
        proposal_version=next_version,
        payload=payload,
    )
    proposal = ValidatorReviewProposal(
        proposal_id=new_validator_review_proposal_id(),
        assignment_id=assignment.assignment_id,
        validator_id=validator.validator_id,
        candidate_id=candidate.candidate_id,
        proposal_version=next_version,
        review_payload=payload["review"],
        recommendation=payload["recommendation"],
        evidence_manifest=payload["evidence_manifest"],
        tokoin_recommendation=payload["tokoin_recommendation"],
        proposal_hash=computed,
        state="AWAITING_OWNER_DECISION",
        supersedes_proposal_id=previous.proposal_id if previous else None,
        created_at=now_utc(),
    )
    session.add(proposal)
    assignment.state = "AWAITING_OWNER_DECISION"
    await session.flush()
    await append_event(
        session,
        event_type="institution.review.proposal_submitted",
        actor={"agent_id": device.agent_id},
        payload={
            "assignment_id": assignment.assignment_id,
            "candidate_id": candidate.candidate_id,
            "validator_id": validator.validator_id,
            "proposal_id": proposal.proposal_id,
            "proposal_version": proposal.proposal_version,
            "proposal_hash": proposal.proposal_hash,
            "verdict_disclosed": False,
            "synthetic_test_only": True,
        },
        trace_id=trace_id,
    )
    return proposal


async def own_review_proposal(
    session: AsyncSession, *, assignment_id: str, device: Device
) -> dict[str, Any]:
    assignment, validator, _ = await _owned_assignment(session, assignment_id, device)
    proposal = await _latest_proposal(session, assignment_id)
    if proposal is None:
        raise NotFound("Review proposal not found.")
    decision = (
        await session.execute(
            select(ValidatorOwnerDecision).where(
                ValidatorOwnerDecision.proposal_id == proposal.proposal_id
            )
        )
    ).scalar_one_or_none()
    return _proposal_view(proposal, assignment, validator, decision)


async def owner_review_proposals(
    session: AsyncSession, *, challenge_id: str, owner: User
) -> dict[str, Any]:
    rows = list(
        (
            await session.execute(
                select(ValidatorAssignment, InstitutionalValidator)
                .join(
                    InstitutionalValidator,
                    InstitutionalValidator.validator_id == ValidatorAssignment.validator_id,
                )
                .join(
                    ResearchCandidateSnapshot,
                    ResearchCandidateSnapshot.candidate_id == ValidatorAssignment.candidate_id,
                )
                .where(
                    ValidatorAssignment.decision_owner_id == owner.user_id,
                    ResearchCandidateSnapshot.challenge_id == challenge_id,
                )
                .order_by(ValidatorAssignment.assigned_at, ValidatorAssignment.assignment_id)
            )
        ).all()
    )
    proposals: list[dict[str, Any]] = []
    pending_analysis = 0
    for assignment, validator in rows:
        proposal = await _latest_proposal(session, assignment.assignment_id)
        if proposal is None:
            if assignment.revealed_at is None:
                pending_analysis += 1
            continue
        decision = (
            await session.execute(
                select(ValidatorOwnerDecision).where(
                    ValidatorOwnerDecision.proposal_id == proposal.proposal_id
                )
            )
        ).scalar_one_or_none()
        proposals.append(_proposal_view(proposal, assignment, validator, decision))
    return {
        "challenge_id": challenge_id,
        "owner_id": owner.user_id,
        "pending_agent_analysis": pending_analysis,
        "proposals": proposals,
        "synthetic_test_only": True,
        "human_validation_satisfied": False,
        "tokoin_settlement_eligible": False,
    }


async def decide_review_proposal(
    session: AsyncSession,
    *,
    proposal_id: str,
    owner: User,
    payload: dict[str, Any],
    trace_id: str | None,
) -> ValidatorOwnerDecision:
    _require_pilot_control_plane()
    proposal = await session.get(ValidatorReviewProposal, proposal_id, with_for_update=True)
    if proposal is None:
        raise NotFound("Review proposal not found.")
    assignment = await session.get(
        ValidatorAssignment, proposal.assignment_id, with_for_update=True
    )
    assert assignment is not None
    if assignment.decision_owner_id != owner.user_id:
        raise OwnerAuthorityRequired("Only the panel operator may decide this proposal.")
    if payload["proposal_hash"] != proposal.proposal_hash:
        raise Conflict("Proposal changed; refresh before recording an Owner decision.")
    existing = (
        await session.execute(
            select(ValidatorOwnerDecision).where(
                ValidatorOwnerDecision.proposal_id == proposal.proposal_id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if (
            existing.decision == payload["decision"]
            and existing.proposal_hash == payload["proposal_hash"]
            and existing.owner_notes == payload["owner_notes"]
        ):
            return existing
        raise Conflict("Owner decision is append-only and cannot be replaced.")
    if (assignment.state != "AWAITING_OWNER_DECISION"
            or proposal.state != "AWAITING_OWNER_DECISION"):
        raise Conflict("Review is no longer awaiting an Owner decision.")
    candidate = await session.get(
        ResearchCandidateSnapshot, proposal.candidate_id, with_for_update=True
    )
    if candidate is None or candidate.state != "INSTITUTIONAL_REVIEW_PENDING":
        raise Conflict("Candidate is no longer pending institutional review.")
    decision_body = {
        "proposal_id": proposal.proposal_id,
        "assignment_id": assignment.assignment_id,
        "owner_id": owner.user_id,
        "decision": payload["decision"],
        "proposal_hash": proposal.proposal_hash,
        "owner_notes": payload["owner_notes"],
    }
    decision = ValidatorOwnerDecision(
        decision_id=new_validator_owner_decision_id(),
        proposal_id=proposal.proposal_id,
        assignment_id=assignment.assignment_id,
        owner_id=owner.user_id,
        decision=payload["decision"],
        proposal_hash=proposal.proposal_hash,
        owner_notes=payload["owner_notes"],
        decision_hash=canonical_json_hash(
            decision_body, domain="agora.institutional.validator.owner-decision.v1"
        ),
        created_at=now_utc(),
    )
    if decision.decision == "APPROVE":
        proposal.state = "OWNER_APPROVED"
        assignment.state = "OWNER_APPROVED_AWAITING_COMMIT"
    elif decision.decision == "REQUEST_REVISION":
        proposal.state = "REVISION_REQUESTED"
        assignment.state = "AWAITING_VALIDATOR_REVISION"
    else:
        proposal.state = "OWNER_REJECTED"
        assignment.state = "OWNER_REJECTED"
    session.add(decision)
    await session.flush()
    await append_event(
        session,
        event_type="institution.review.owner_decision_recorded",
        actor={"agent_id": SYSTEM_ACTOR_ID},
        payload={
            "assignment_id": assignment.assignment_id,
            "candidate_id": proposal.candidate_id,
            "proposal_id": proposal.proposal_id,
            "proposal_hash": proposal.proposal_hash,
            "owner_id": owner.user_id,
            "decision": decision.decision,
            "decision_hash": decision.decision_hash,
            "synthetic_test_only": True,
            "tokoin_released": False,
        },
        trace_id=trace_id,
    )
    return decision


async def commit_review(
    session: AsyncSession,
    *,
    assignment_id: str,
    device: Device,
    payload: dict[str, Any],
    trace_id: str | None,
) -> ValidatorAssignment:
    _require_pilot_control_plane()
    assignment, validator, candidate = await _owned_assignment(
        session, assignment_id, device, lock=True
    )
    if assignment.state == "CONFLICT_DECLARED":
        raise Conflict("Conflicted assignment must be reassigned before review.")
    try:
        Ed25519PublicKey.from_public_bytes(_b64url_decode(validator.public_key)).verify(
            _b64url_decode(payload["commitment_signature"]),
            payload["commitment_hash"].encode("ascii"),
        )
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise OwnerAuthorityRequired("Review commitment signature is invalid.") from exc
    if assignment.committed_at is not None:
        if (
            assignment.commitment_hash == payload["commitment_hash"]
            and assignment.commitment_signature == payload["commitment_signature"]
        ):
            return assignment
        raise Conflict("Review commitment is immutable.")
    proposal = await _latest_proposal(session, assignment.assignment_id, lock=True)
    if proposal is None or proposal.state != "OWNER_APPROVED":
        raise OwnerAuthorityRequired(
            "The assigned Owner must approve the exact validator proposal before commit."
        )
    expected_commitment = review_commitment(
        assignment, validator, candidate, proposal.review_payload
    )
    if payload["commitment_hash"] != expected_commitment:
        raise Conflict("Commitment does not match the Owner-approved proposal hash.")
    assignment.commitment_hash = payload["commitment_hash"]
    assignment.commitment_signature = payload["commitment_signature"]
    assignment.conflict_declaration = payload["conflict_declaration"]
    assignment.committed_at = now_utc()
    assignment.state = "VERDICT_COMMITTED"
    await append_event(
        session,
        event_type="institution.review.started",
        actor={"agent_id": device.agent_id},
        payload={
            "assignment_id": assignment_id,
            "validator_id": validator.validator_id,
            "candidate_id": candidate.candidate_id,
            "candidate_version": candidate.candidate_version,
            "blind_review": True,
            "synthetic": True,
        },
        trace_id=trace_id,
    )
    if validator.review_role == "REPRODUCTION_METHODOLOGY":
        await append_event(
            session,
            event_type="institution.reproduction.started",
            actor={"agent_id": device.agent_id},
            payload={
                "assignment_id": assignment_id,
                "validator_id": validator.validator_id,
                "candidate_id": candidate.candidate_id,
                "candidate_version": candidate.candidate_version,
                "synthetic": True,
            },
            trace_id=trace_id,
        )
    await append_event(
        session,
        event_type="institution.review.committed",
        actor={"agent_id": device.agent_id},
        payload={
            "assignment_id": assignment_id,
            "validator_id": validator.validator_id,
            "candidate_id": candidate.candidate_id,
            "commitment_hash": assignment.commitment_hash,
            "draft_disclosed": False,
        },
        trace_id=trace_id,
    )
    return assignment


def _panel_result(verdicts: set[str]) -> str:
    if "INSUFFICIENT_EVIDENCE" in verdicts:
        return "EVIDENCE_REVIEW_REQUIRED"
    if verdicts == {"APPROVED"}:
        return "AGORA_PROTOCOL_VALIDATED_TEST"
    if verdicts <= POSITIVE:
        return "MINOR_REVISION_GATE"
    if verdicts == {"REJECTED"}:
        return "CANDIDATE_REJECTED"
    if "REJECTED" in verdicts and verdicts & POSITIVE:
        return "VALIDATION_CONFLICT"
    return "RETURN_TO_RESEARCH"


async def _materialize_revealed_review(
    session: AsyncSession,
    *,
    candidate: ResearchCandidateSnapshot,
    review: ValidatorReview,
    validator: InstitutionalValidator,
    trace_id: str | None,
) -> None:
    if review.genealogy_node_id is not None:
        return
    agent = await session.get(Agent, validator.actor_id)
    assert agent is not None
    review_node = await create_object(
        session,
        agent=agent,
        payload={
            "object_type": "institutional_review",
            "challenge_id": candidate.challenge_id,
            "visibility_lane": "OPEN",
            "rights_status": "explicit_open_license",
            "license_id": "CC-BY-4.0",
            "payload": {
                "title": f"Synthetic blind review {review.review_id}",
                "review_id": review.review_id,
                "candidate_id": candidate.candidate_id,
                "candidate_version": candidate.candidate_version,
                "verdict": review.verdict,
                "confidence": review.confidence,
                "reproduction_status": review.reproduction_status,
                "review_hash": review.review_hash,
                "synthetic_test_review": True,
                "disclaimer": PILOT_DISCLAIMER,
            },
            "parent_object_ids": [candidate.final_solution_object_id],
            "idempotency_key": f"validator-review:{review.review_id}",
            "state": "SUPPORTED_ONCE" if review.verdict in POSITIVE else "CONTESTED",
        },
        trace_id=trace_id,
    )
    review.genealogy_node_id = review_node.object_id
    relation = "approves_version" if review.verdict in POSITIVE else "requests_revision_of"
    await create_edge(
        session,
        agent=agent,
        payload={
            "source_object_id": review_node.object_id,
            "target_object_id": candidate.final_solution_object_id,
            "relation_type": relation,
            "payload": {"candidate_id": candidate.candidate_id, "synthetic": True},
            "idempotency_key": f"validator-review-edge:{review.review_id}",
        },
        trace_id=trace_id,
    )
    reproduction_supported = review.reproduction_status in FINAL_REPRODUCTION_STATUSES
    if review.reproduction_status == "REPRODUCED":
        reproduction_state = "REPLICATED"
    elif review.reproduction_status == "PARTIALLY_REPRODUCED":
        reproduction_state = "SUPPORTED_ONCE"
    elif review.reproduction_status == "FAILED_TO_REPRODUCE":
        reproduction_state = "REFUTED"
    else:
        reproduction_state = "INCONCLUSIVE"
    reproduction_node = await create_object(
        session,
        agent=agent,
        payload={
            "object_type": "reproduction_result",
            "challenge_id": candidate.challenge_id,
            "visibility_lane": "OPEN",
            "rights_status": "explicit_open_license",
            "license_id": "CC-BY-4.0",
            "payload": {
                "title": "Independent synthetic reproduction result",
                "review_id": review.review_id,
                "reproduction_status": review.reproduction_status,
                "executed_tests": review.executed_tests,
                "findings": review.reproduction_findings,
            },
            "parent_object_ids": [candidate.final_solution_object_id],
            "idempotency_key": f"validator-reproduction:{review.review_id}",
            "state": reproduction_state,
        },
        trace_id=trace_id,
    )
    await create_edge(
        session,
        agent=agent,
        payload={
            "source_object_id": reproduction_node.object_id,
            "target_object_id": candidate.final_solution_object_id,
            "relation_type": (
                "reproduces"
                if reproduction_supported
                else "fails_to_reproduce"
                if review.reproduction_status == "FAILED_TO_REPRODUCE"
                else "reviews"
            ),
            "payload": {"review_id": review.review_id},
            "idempotency_key": f"validator-reproduction-edge:{review.review_id}",
        },
        trace_id=trace_id,
    )
    history = dict(validator.review_history or {})
    history["completed"] = int(history.get("completed", 0)) + 1
    history["reproductions"] = int(history.get("reproductions", 0)) + 1
    key = "approved" if review.verdict in POSITIVE else "adverse"
    history[key] = int(history.get(key, 0)) + 1
    validator.review_history = history
    validator.reputation_score = min(1000, validator.reputation_score + 10)
    await append_event(
        session,
        event_type="institution.review.revealed",
        actor={"agent_id": validator.actor_id},
        payload={
            "review_id": review.review_id,
            "candidate_id": candidate.candidate_id,
            "validator_id": validator.validator_id,
            "verdict": review.verdict,
            "review_hash": review.review_hash,
            "synthetic": True,
        },
        trace_id=trace_id,
    )
    await append_event(
        session,
        event_type="institution.review.finding_created",
        actor={"agent_id": validator.actor_id},
        payload={
            "review_id": review.review_id,
            "candidate_id": candidate.candidate_id,
            "finding_types": ["methodology", "reproduction", "evidence"],
            "review_hash": review.review_hash,
            "synthetic": True,
        },
        trace_id=trace_id,
    )
    await append_event(
        session,
        event_type="institution.reproduction.completed",
        actor={"agent_id": validator.actor_id},
        payload={
            "review_id": review.review_id,
            "reproduction_status": review.reproduction_status,
            "synthetic": True,
        },
        trace_id=trace_id,
    )
    await append_event(
        session,
        event_type=(
            "institution.review.approved"
            if review.verdict in POSITIVE
            else "institution.review.revision_requested"
        ),
        actor={"agent_id": validator.actor_id},
        payload={
            "review_id": review.review_id,
            "candidate_id": candidate.candidate_id,
            "verdict": review.verdict,
            "synthetic": True,
        },
        trace_id=trace_id,
    )


async def reveal_review(
    session: AsyncSession,
    *,
    assignment_id: str,
    device: Device,
    payload: dict[str, Any],
    trace_id: str | None,
) -> ValidatorReview:
    _require_pilot_control_plane()
    assignment, validator, candidate = await _owned_assignment(
        session, assignment_id, device, lock=True
    )
    if assignment.committed_at is None or assignment.commitment_hash is None:
        raise Conflict("Commit the blind review hash before revealing it.")
    proposal = await _latest_proposal(session, assignment.assignment_id)
    if proposal is None or proposal.state != "OWNER_APPROVED":
        raise OwnerAuthorityRequired("Owner approval is missing for this revealed review.")
    approved_hash = review_commitment(
        assignment, validator, candidate, proposal.review_payload
    )
    if approved_hash != assignment.commitment_hash:
        raise Conflict("Committed review no longer matches the Owner-approved proposal.")
    panel = list(
        (
            await session.execute(
                select(ValidatorAssignment)
                .where(ValidatorAssignment.candidate_id == candidate.candidate_id)
                .with_for_update()
            )
        ).scalars()
    )
    if len(panel) != 2 or any(row.committed_at is None for row in panel):
        raise Conflict("Peer verdict remains sealed until both validators commit.")
    computed = review_commitment(assignment, validator, candidate, payload)
    if computed != assignment.commitment_hash:
        raise ValidationFailed("Revealed review does not match its immutable commitment.")
    _validate_review_consistency(validator, payload)
    existing = (
        await session.execute(
            select(ValidatorReview).where(ValidatorReview.assignment_id == assignment_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.review_hash == computed:
            return existing
        raise Conflict("Revealed review is immutable.")
    review = ValidatorReview(
        review_id=new_validator_review_id(),
        assignment_id=assignment.assignment_id,
        validator_id=validator.validator_id,
        candidate_id=candidate.candidate_id,
        verdict=payload["verdict"],
        confidence=payload["confidence"],
        reproduction_status=payload["reproduction_status"],
        dimensions=payload["dimensions"],
        summary=payload["summary"],
        methodology_findings=payload["methodology_findings"],
        reproduction_findings=payload["reproduction_findings"],
        evidence_findings=payload["evidence_findings"],
        critical_issues=payload["critical_issues"],
        minor_issues=payload["minor_issues"],
        requested_changes=payload["requested_changes"],
        executed_tests=payload["executed_tests"],
        artifacts_reviewed=payload["artifacts_reviewed"],
        review_hash=computed,
        created_at=now_utc(),
    )
    session.add(review)
    assignment.state = "VERDICT_REVEALED"
    assignment.revealed_at = now_utc()
    await session.flush()
    await append_event(
        session,
        event_type="institution.review.reveal_received",
        actor={"agent_id": device.agent_id},
        payload={
            "review_id": review.review_id,
            "candidate_id": candidate.candidate_id,
            "validator_id": validator.validator_id,
            "review_hash": review.review_hash,
            "verdict_disclosed": False,
            "synthetic": True,
        },
        trace_id=trace_id,
    )
    revealed_verdicts = list(
        (
            await session.execute(
                select(ValidatorReview.verdict).where(
                    ValidatorReview.candidate_id == candidate.candidate_id
                )
            )
        ).scalars()
    )
    if len(revealed_verdicts) == len(panel) == 2:
        revealed_reviews = list(
            (
                await session.execute(
                    select(ValidatorReview).where(
                        ValidatorReview.candidate_id == candidate.candidate_id
                    )
                )
            ).scalars()
        )
        validator_by_id = {
            row.validator_id: row
            for row in (
                await session.execute(
                    select(InstitutionalValidator).where(
                        InstitutionalValidator.validator_id.in_(
                            [item.validator_id for item in revealed_reviews]
                        )
                    )
                )
            ).scalars()
        }
        for revealed in revealed_reviews:
            await _materialize_revealed_review(
                session,
                candidate=candidate,
                review=revealed,
                validator=validator_by_id[revealed.validator_id],
                trace_id=trace_id,
            )
        result = _panel_result(set(revealed_verdicts))
        event_type = (
            "institution.validation.quorum_reached"
            if result == "AGORA_PROTOCOL_VALIDATED_TEST"
            else "institution.validation.conflict_detected"
        )
        await append_event(
            session,
            event_type=event_type,
            actor={"agent_id": SYSTEM_ACTOR_ID},
            payload={
                "candidate_id": candidate.candidate_id,
                "result": result,
                "synthetic_test_only": True,
                "human_validation_satisfied": False,
                "tokoin_released": False,
            },
            trace_id=trace_id,
        )
    return review


async def panel_view(session: AsyncSession, candidate_id: str) -> dict[str, Any]:
    assignments = list(
        (
            await session.execute(
                select(ValidatorAssignment, InstitutionalValidator)
                .join(
                    InstitutionalValidator,
                    InstitutionalValidator.validator_id == ValidatorAssignment.validator_id,
                )
                .where(ValidatorAssignment.candidate_id == candidate_id)
                .order_by(ValidatorAssignment.assigned_at, ValidatorAssignment.assignment_id)
            )
        ).all()
    )
    reviews = {
        row.assignment_id: row
        for row in (
            await session.execute(
                select(ValidatorReview).where(ValidatorReview.candidate_id == candidate_id)
            )
        ).scalars()
    }
    proposal_rows = list(
        (
            await session.execute(
                select(ValidatorReviewProposal)
                .where(ValidatorReviewProposal.candidate_id == candidate_id)
                .order_by(
                    ValidatorReviewProposal.assignment_id,
                    ValidatorReviewProposal.proposal_version.desc(),
                )
            )
        ).scalars()
    )
    proposals: dict[str, ValidatorReviewProposal] = {}
    for proposal in proposal_rows:
        proposals.setdefault(proposal.assignment_id, proposal)
    all_committed = len(assignments) == 2 and all(
        row.committed_at is not None for row, _ in assignments
    )
    all_revealed = len(assignments) == 2 and all(
        row.revealed_at is not None for row, _ in assignments
    )
    candidate = await session.get(ResearchCandidateSnapshot, candidate_id)
    reward = (
        await session.execute(
            select(ResearchRewardCalculation).where(
                ResearchRewardCalculation.candidate_id == candidate_id
            )
        )
    ).scalar_one_or_none()
    credit = 0
    if reward is not None and assignments:
        credit = (
            int(reward.allocation.get("pools", {}).get("institutional_validation_pool", 0)) // 2
        )
    proposal_states = {row.state for row in proposals.values()}
    if all_revealed:
        status = _panel_result({row.verdict for row in reviews.values()})
    elif all_committed:
        status = "COMMITTED_AWAITING_REVEAL"
    elif any(row.state == "OWNER_REJECTED" for row, _ in assignments):
        status = "OWNER_REJECTED"
    elif "REVISION_REQUESTED" in proposal_states:
        status = "AWAITING_VALIDATOR_REVISION"
    elif len(proposals) == 2 and proposal_states == {"OWNER_APPROVED"}:
        status = "OWNER_APPROVED_AWAITING_COMMIT"
    elif proposals:
        status = "AWAITING_OWNER_DECISION"
    elif assignments:
        status = "AGENT_ANALYSIS_IN_PROGRESS"
    else:
        status = "UNASSIGNED"
    return {
        "candidate_id": candidate_id,
        "candidate_state": candidate.state if candidate else None,
        "blind_review": True,
        "minimum_validators": 2,
        "all_committed": all_committed,
        "all_revealed": all_revealed,
        "status": status,
        "synthetic_test_only": True,
        "human_validation_satisfied": False,
        "tokoin_settlement_eligible": False,
        "pilot_credit_per_completed_review_aceros": credit,
        "pilot_credit_is_non_settleable": True,
        "tracks": [
            _assignment_view(
                row,
                validator,
                reviews.get(row.assignment_id),
                proposals.get(row.assignment_id),
                reveal_details=all_revealed,
            )
            for row, validator in assignments
        ],
    }


async def my_assignments(session: AsyncSession, device: Device) -> dict[str, Any]:
    validator = (
        await session.execute(
            select(InstitutionalValidator).where(InstitutionalValidator.actor_id == device.agent_id)
        )
    ).scalar_one_or_none()
    if validator is None:
        raise OwnerAuthorityRequired("Agent is not an Institutional Validator.")
    rows = list(
        (
            await session.execute(
                select(ValidatorAssignment).where(
                    ValidatorAssignment.validator_id == validator.validator_id
                )
            )
        ).scalars()
    )
    result = []
    for row in rows:
        panel = await panel_view(session, row.candidate_id)
        own = next(
            track for track in panel["tracks"] if track["assignment_id"] == row.assignment_id
        )
        result.append(
            {
                **own,
                "peer_status": [
                    {
                        "committed": track["committed"],
                        "revealed": track["revealed"],
                        "state": track["state"],
                    }
                    for track in panel["tracks"]
                    if track["assignment_id"] != row.assignment_id
                ],
            }
        )
    return {"validator": validator_view(validator), "assignments": result}
