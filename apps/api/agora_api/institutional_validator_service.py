"""Blind synthetic institutional-review pilot.

Pilot validators are authenticated Agents with an additional, explicit actor
record. Their reviews exercise AGORA's protocol but never satisfy human
validation, publication, or TOKOIN settlement gates.
"""

from __future__ import annotations

import base64
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.config import get_settings
from agora_api.errors import Conflict, NotFound, OwnerAuthorityRequired, ValidationFailed
from agora_api.events import append_event, now_utc
from agora_api.ids import (
    new_institutional_validator_id,
    new_validator_assignment_id,
    new_validator_review_id,
)
from agora_api.magna_knowledge_ledger import canonical_json_hash, create_edge, create_object
from agora_api.models import (
    Agent,
    Device,
    InstitutionalValidator,
    MagnaKnowledgeObject,
    Mission,
    MissionChallengeSubmission,
    ResearchCandidateSnapshot,
    ResearchRewardCalculation,
    User,
    ValidatorAssignment,
    ValidatorReview,
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
    *,
    reveal_details: bool,
) -> dict[str, Any]:
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
    assignment, validator, candidate = await _owned_assignment(session, assignment_id, device)
    mission = await session.get(Mission, candidate.challenge_id)
    submission = await session.get(MissionChallengeSubmission, candidate.submission_id)
    solution = await session.get(MagnaKnowledgeObject, candidate.final_solution_object_id)
    assert mission is not None and submission is not None and solution is not None
    solution_payload = solution.payload if solution.visibility_lane == "OPEN" else None
    return {
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
    }


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
    if all_revealed:
        status = _panel_result({row.verdict for row in reviews.values()})
    elif all_committed:
        status = "COMMITTED_AWAITING_REVEAL"
    elif assignments:
        status = "BLIND_REVIEW_IN_PROGRESS"
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
                row, validator, reviews.get(row.assignment_id), reveal_details=all_revealed
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
