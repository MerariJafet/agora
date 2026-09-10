"""AGORA Research Protocol v1.

Agent consensus freezes a candidate. It never proves truth and never releases
TOKOIN. Human institutional reviews bind to the exact candidate hash; reward
locking requires two independent approved reviews.
"""

from __future__ import annotations

import base64
from collections import defaultdict
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
    new_institution_id,
    new_institutional_review_id,
    new_research_candidate_id,
    new_research_publication_package_id,
    new_research_reward_id,
    new_research_score_id,
)
from agora_api.magna_knowledge_ledger import canonical_json_hash
from agora_api.models import (
    InstitutionalReview,
    MagnaKnowledgeEdge,
    MagnaKnowledgeObject,
    Mission,
    MissionChallengeSubmission,
    MissionChallengeVote,
    MissionParticipant,
    ResearchCandidateSnapshot,
    ResearchContributionScore,
    ResearchInstitution,
    ResearchPublicationPackage,
    ResearchRewardCalculation,
    User,
)
from agora_api.provenance import SYSTEM_ACTOR_ID
from agora_api.science_scope import assess_solution_scope

PROTOCOL_VERSION = "1.0.0"
SCORING_VERSION = "AGORA_CONTRIBUTION_SCORE_V1"
APPROVAL_VERDICTS = {"APPROVED", "APPROVED_WITH_MINOR_CHANGES"}
ADVERSE_VERDICTS = {"REQUIRES_REVISION", "REJECTED", "INSUFFICIENT_EVIDENCE"}
REWARD_PERCENT = {
    "research_proposer": 1,
    "final_solution": 10,
    "participant_contribution_pool": 60,
    "institutional_validation_pool": 20,
    "agora_infrastructure": 9,
}
WEIGHTS_BPS = {
    "novelty": 1000,
    "correctness": 1500,
    "reproducibility": 2000,
    "downstream_dependency": 1000,
    "methodological_value": 1000,
    "error_detection_value": 1000,
    "experimental_value": 1000,
    "information_gain": 500,
    "independent_validation": 500,
    "final_solution_proximity": 500,
}

TYPE_SIGNAL: dict[str, dict[str, int]] = {
    "hypothesis": {"novelty": 700, "information_gain": 500},
    "method": {"methodological_value": 800, "reproducibility": 400},
    "experiment_proposal": {"methodological_value": 700, "experimental_value": 500},
    "experiment_run": {"experimental_value": 800, "reproducibility": 500},
    "experiment_result": {"experimental_value": 900, "correctness": 500},
    "replication": {"reproducibility": 1000, "independent_validation": 800},
    "refutation": {"error_detection_value": 1000, "correctness": 700},
    "counterexample": {"error_detection_value": 1000, "correctness": 800},
    "correction": {"error_detection_value": 800, "methodological_value": 600},
    "proof": {"correctness": 900, "reproducibility": 700},
    "dataset": {"experimental_value": 500, "reproducibility": 500},
    "synthesis": {"downstream_dependency": 500, "information_gain": 600},
    "candidate_solution": {"final_solution_proximity": 900, "correctness": 600},
    "final_solution": {"final_solution_proximity": 1000, "correctness": 700},
}


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _candidate_view(row: ResearchCandidateSnapshot) -> dict[str, Any]:
    return {
        "candidate_id": row.candidate_id,
        "challenge_id": row.challenge_id,
        "submission_id": row.submission_id,
        "candidate_version": row.candidate_version,
        "state": row.state,
        "final_solution_object_id": row.final_solution_object_id,
        "manuscript_artifact_version_id": row.manuscript_artifact_version_id,
        "knowledge_root_hash": row.knowledge_root_hash,
        "consensus_snapshot": row.consensus_snapshot,
        "protocol_version": row.protocol_version,
        "content_hash": row.content_hash,
        "created_by_agent_id": row.created_by_agent_id,
        "created_at": row.created_at.isoformat(),
    }


def institution_view(row: ResearchInstitution, *, public: bool = True) -> dict[str, Any]:
    result = {
        "institution_id": row.institution_id,
        "legal_entity_id": row.legal_entity_id,
        "name": row.name,
        "domain": row.domain,
        "jurisdiction": row.jurisdiction,
        "state": row.state,
        "credential_hash": row.credential_hash,
        "payout_address_configured": bool(row.payout_address),
        "created_at": row.created_at.isoformat(),
        "activated_at": row.activated_at.isoformat() if row.activated_at else None,
    }
    if not public:
        result["representative_owner_id"] = row.representative_owner_id
        result["credential_reference"] = row.credential_reference
        result["conflict_metadata"] = row.conflict_metadata
    return result


def review_signing_payload(candidate: ResearchCandidateSnapshot, payload: dict[str, Any]) -> dict:
    return {
        "domain": "agora.institutional.review.v1",
        "candidate_id": candidate.candidate_id,
        "candidate_content_hash": candidate.content_hash,
        "institution_id": payload["institution_id"],
        "verdict": payload["verdict"],
        "methodology_review": payload["methodology_review"],
        "evidence_review": payload["evidence_review"],
        "paper_review": payload["paper_review"],
        "experiment_review": payload["experiment_review"],
        "conflict_declaration": payload["conflict_declaration"],
    }


async def register_institution(
    session: AsyncSession, *, owner: User, payload: dict[str, Any], trace_id: str | None
) -> ResearchInstitution:
    try:
        key = _b64url_decode(payload["signing_public_key"])
        Ed25519PublicKey.from_public_bytes(key)
    except (ValueError, TypeError) as exc:
        raise ValidationFailed(
            "Institution signing_public_key must be a raw Ed25519 public key."
        ) from exc
    row = ResearchInstitution(
        institution_id=new_institution_id(),
        legal_entity_id=payload["legal_entity_id"],
        name=payload["name"],
        domain=payload["domain"].lower(),
        jurisdiction=payload["jurisdiction"],
        representative_owner_id=owner.user_id,
        signing_public_key=payload["signing_public_key"],
        credential_reference=payload["credential_reference"],
        credential_hash=payload["credential_hash"],
        payout_address=payload.get("payout_address"),
        conflict_metadata=payload.get("conflict_metadata", {}),
        state="PENDING",
        created_at=now_utc(),
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise Conflict(
            "Institution legal identity or representative is already registered."
        ) from exc
    await append_event(
        session,
        event_type="institution.registration.requested",
        actor={"agent_id": SYSTEM_ACTOR_ID},
        payload={
            "institution_id": row.institution_id,
            "representative_owner_id": owner.user_id,
            "credential_hash": row.credential_hash,
        },
        trace_id=trace_id,
    )
    return row


async def verify_institution(
    session: AsyncSession,
    *,
    institution_id: str,
    verifier: User,
    verification_evidence_hash: str,
    trace_id: str | None,
) -> ResearchInstitution:
    settings = get_settings()
    if settings.is_production or not settings.institutional_registry_control_plane_enabled:
        raise OwnerAuthorityRequired("Institution verification control plane is disabled.")
    row = await session.get(ResearchInstitution, institution_id, with_for_update=True)
    if row is None:
        raise NotFound("Institution not found.")
    if row.representative_owner_id == verifier.user_id:
        raise OwnerAuthorityRequired(
            "An institution representative cannot verify its own institution."
        )
    if row.state == "ACTIVE":
        return row
    if row.state != "PENDING":
        raise Conflict("Only pending institutions can be activated.")
    row.state = "ACTIVE"
    row.verified_by_owner_id = verifier.user_id
    row.activated_at = now_utc()
    await append_event(
        session,
        event_type="institution.verified",
        actor={"agent_id": SYSTEM_ACTOR_ID},
        payload={
            "institution_id": row.institution_id,
            "verifier_owner_id": verifier.user_id,
            "verification_evidence_hash": verification_evidence_hash,
        },
        trace_id=trace_id,
    )
    return row


async def _knowledge_material(session: AsyncSession, challenge_id: str) -> tuple[list, list, str]:
    objects = list(
        (
            await session.execute(
                select(MagnaKnowledgeObject)
                .where(MagnaKnowledgeObject.challenge_id == challenge_id)
                .order_by(MagnaKnowledgeObject.created_at, MagnaKnowledgeObject.object_id)
            )
        ).scalars()
    )
    object_ids = [row.object_id for row in objects]
    edges: list[MagnaKnowledgeEdge] = []
    if object_ids:
        edges = list(
            (
                await session.execute(
                    select(MagnaKnowledgeEdge)
                    .where(
                        MagnaKnowledgeEdge.source_object_id.in_(object_ids),
                        MagnaKnowledgeEdge.target_object_id.in_(object_ids),
                        MagnaKnowledgeEdge.retracted_at.is_(None),
                    )
                    .order_by(MagnaKnowledgeEdge.created_at, MagnaKnowledgeEdge.edge_id)
                )
            ).scalars()
        )
    root = canonical_json_hash(
        {
            "objects": [row.canonical_content_hash for row in objects],
            "edges": [row.canonical_content_hash for row in edges],
        },
        domain="agora.research.genealogy.root.v1",
    )
    return objects, edges, root


async def create_candidate(
    session: AsyncSession,
    *,
    challenge_id: str,
    agent_id: str,
    agent_version_id: str | None,
    payload: dict[str, Any],
    trace_id: str | None,
) -> ResearchCandidateSnapshot:
    mission = await session.get(Mission, challenge_id, with_for_update=True)
    existing_retry = (
        await session.execute(
            select(ResearchCandidateSnapshot).where(
                ResearchCandidateSnapshot.challenge_id == challenge_id,
                ResearchCandidateSnapshot.idempotency_key == payload["idempotency_key"],
            )
        )
    ).scalar_one_or_none()
    if existing_retry is not None:
        if existing_retry.created_by_agent_id != agent_id:
            raise Conflict("Candidate idempotency key belongs to another Agent.")
        return existing_retry
    submission = await session.get(MissionChallengeSubmission, payload["submission_id"])
    solution = await session.get(MagnaKnowledgeObject, payload["final_solution_object_id"])
    if mission is None or mission.challenge_kind is None:
        raise NotFound("Research challenge not found.")
    if submission is None or submission.mission_id != challenge_id:
        raise NotFound("Challenge submission not found.")
    beneficiaries = set(submission.team_agent_ids or [submission.agent_id])
    if agent_id not in beneficiaries:
        raise OwnerAuthorityRequired("Only a submission beneficiary can freeze its candidate.")
    scope = assess_solution_scope(mission, submission)
    if not scope["eligible_for_full_resolution"]:
        raise Conflict("Candidate scope is incomplete: " + ", ".join(scope["blockers"]))
    if solution is None or solution.challenge_id != challenge_id:
        raise ValidationFailed("Final solution object must belong to this challenge.")
    solution_types = {"candidate_solution", "final_solution", "outcome", "proof", "refutation"}
    if solution.object_type not in solution_types:
        raise ValidationFailed("Knowledge object is not a candidate-solution type.")
    participant_ids = (
        set(
            (
                await session.execute(
                    select(MissionParticipant.agent_id).where(
                        MissionParticipant.mission_id == challenge_id,
                        MissionParticipant.left_at.is_(None),
                    )
                )
            ).scalars()
        )
        - beneficiaries
    )
    votes = list(
        (
            await session.execute(
                select(MissionChallengeVote).where(
                    MissionChallengeVote.submission_id == submission.submission_id,
                    MissionChallengeVote.voter_agent_id.in_(participant_ids),
                )
            )
        ).scalars()
    )
    vote_by_agent = {row.voter_agent_id: row for row in votes}
    decisive = [row for row in votes if not row.abstained]
    if participant_ids - set(vote_by_agent):
        raise Conflict("All active reviewers must vote or explicitly abstain before consensus.")
    if len(decisive) < 2 or any(not row.resolved for row in decisive):
        raise Conflict("Candidate requires at least two unanimous decisive agent reviews.")
    _, _, root = await _knowledge_material(session, challenge_id)
    existing = list(
        (
            await session.execute(
                select(ResearchCandidateSnapshot)
                .where(ResearchCandidateSnapshot.challenge_id == challenge_id)
                .order_by(ResearchCandidateSnapshot.candidate_version.desc())
            )
        ).scalars()
    )
    version = (existing[0].candidate_version + 1) if existing else 1
    consensus = {
        "meaning": "agent_perception_not_scientific_truth",
        "submission_id": submission.submission_id,
        "participant_ids": sorted(participant_ids),
        "votes": [
            {
                "voter_agent_id": row.voter_agent_id,
                "verdict": row.verdict or ("resolved" if row.resolved else "not_resolved"),
                "abstained": row.abstained,
                "evidence_ids": row.review_evidence_ids or [],
                "rationale_hash": canonical_json_hash(
                    row.rationale, domain="agora.vote.rationale.v1"
                ),
            }
            for row in sorted(votes, key=lambda item: item.voter_agent_id)
        ],
    }
    body = {
        "challenge_id": challenge_id,
        "submission_id": submission.submission_id,
        "candidate_version": version,
        "final_solution_hash": solution.canonical_content_hash,
        "manuscript_artifact_version_id": payload.get("manuscript_artifact_version_id"),
        "knowledge_root_hash": root,
        "consensus_snapshot": consensus,
        "protocol_version": PROTOCOL_VERSION,
    }
    row = ResearchCandidateSnapshot(
        candidate_id=new_research_candidate_id(),
        challenge_id=challenge_id,
        submission_id=submission.submission_id,
        candidate_version=version,
        state="INSTITUTIONAL_REVIEW_PENDING",
        final_solution_object_id=solution.object_id,
        manuscript_artifact_version_id=payload.get("manuscript_artifact_version_id"),
        knowledge_root_hash=root,
        consensus_snapshot=consensus,
        protocol_version=PROTOCOL_VERSION,
        idempotency_key=payload["idempotency_key"],
        content_hash=canonical_json_hash(body, domain="agora.research.candidate.v1"),
        created_by_agent_id=agent_id,
        created_by_agent_version_id=agent_version_id,
        created_at=now_utc(),
    )
    session.add(row)
    await session.flush()
    candidate_events = (
        "consensus.reached",
        "candidate.solution.created",
        "institution.review.requested",
    )
    for event_type in candidate_events:
        await append_event(
            session,
            event_type=event_type,
            actor={"agent_id": agent_id, "agent_version_id": agent_version_id},
            payload={
                "challenge_id": challenge_id,
                "candidate_id": row.candidate_id,
                "candidate_hash": row.content_hash,
            },
            trace_id=trace_id,
        )
    return row


async def create_review(
    session: AsyncSession,
    *,
    candidate_id: str,
    owner: User,
    payload: dict[str, Any],
    trace_id: str | None,
) -> InstitutionalReview:
    candidate = await session.get(ResearchCandidateSnapshot, candidate_id)
    institution = await session.get(ResearchInstitution, payload["institution_id"])
    if candidate is None:
        raise NotFound("Research candidate not found.")
    if institution is None or institution.state != "ACTIVE":
        raise OwnerAuthorityRequired("Institution is not active.")
    if institution.representative_owner_id != owner.user_id:
        raise OwnerAuthorityRequired("Owner is not the institution representative.")
    signing_payload = review_signing_payload(candidate, payload)
    signed_hash = canonical_json_hash(
        signing_payload, domain="agora.institutional.review.payload.v1"
    )
    try:
        Ed25519PublicKey.from_public_bytes(_b64url_decode(institution.signing_public_key)).verify(
            _b64url_decode(payload["signature"]), signed_hash.encode("ascii")
        )
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise OwnerAuthorityRequired("Institutional review signature is invalid.") from exc
    body = {**signing_payload, "signed_payload_hash": signed_hash}
    row = InstitutionalReview(
        review_id=new_institutional_review_id(),
        institution_id=institution.institution_id,
        candidate_id=candidate.candidate_id,
        verdict=payload["verdict"],
        methodology_review=payload["methodology_review"],
        evidence_review=payload["evidence_review"],
        paper_review=payload["paper_review"],
        experiment_review=payload["experiment_review"],
        conflict_declaration=payload["conflict_declaration"],
        signed_payload_hash=signed_hash,
        signature=payload["signature"],
        content_hash=canonical_json_hash(body, domain="agora.institutional.review.v1"),
        created_at=now_utc(),
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise Conflict("Institution already reviewed this exact candidate.") from exc
    candidate.state = (
        "REVISION_REQUESTED" if row.verdict in ADVERSE_VERDICTS else "INSTITUTIONAL_REVIEW_ACTIVE"
    )
    await append_event(
        session,
        event_type="institution.review.completed",
        actor={"agent_id": SYSTEM_ACTOR_ID},
        payload={
            "candidate_id": candidate.candidate_id,
            "candidate_hash": candidate.content_hash,
            "institution_id": institution.institution_id,
            "representative_owner_id": owner.user_id,
            "verdict": row.verdict,
            "review_hash": row.content_hash,
        },
        trace_id=trace_id,
    )
    if row.verdict == "REQUIRES_REVISION":
        await append_event(
            session,
            event_type="institution.revision.requested",
            actor={"agent_id": SYSTEM_ACTOR_ID},
            payload={
                "candidate_id": candidate.candidate_id,
                "review_id": row.review_id,
                "institution_id": institution.institution_id,
            },
            trace_id=trace_id,
        )
    return row


async def prepare_review_signing_payload(
    session: AsyncSession,
    *,
    candidate_id: str,
    owner: User,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Return the exact digest for an institution's external secure signer."""
    candidate = await session.get(ResearchCandidateSnapshot, candidate_id)
    institution = await session.get(ResearchInstitution, payload["institution_id"])
    if candidate is None:
        raise NotFound("Research candidate not found.")
    if institution is None or institution.state != "ACTIVE":
        raise OwnerAuthorityRequired("Institution is not active.")
    if institution.representative_owner_id != owner.user_id:
        raise OwnerAuthorityRequired("Owner is not the institution representative.")
    signing_payload = review_signing_payload(candidate, payload)
    return {
        "signature_algorithm": "Ed25519",
        "candidate_content_hash": candidate.content_hash,
        "signing_payload": signing_payload,
        "signed_payload_hash": canonical_json_hash(
            signing_payload, domain="agora.institutional.review.payload.v1"
        ),
        "instruction": "Sign the ASCII bytes of signed_payload_hash outside AGORA.",
    }


def _dimensions_for(row: MagnaKnowledgeObject, inbound: int, validation: int) -> dict[str, int]:
    dimensions = {name: 0 for name in WEIGHTS_BPS}
    for name, value in TYPE_SIGNAL.get(row.object_type, {}).items():
        dimensions[name] = value
    dimensions["downstream_dependency"] = min(1000, inbound * 150)
    dimensions["independent_validation"] = min(1000, validation * 250)
    if row.state in {"REPLICATED", "RESOLVED_VERIFIED"}:
        dimensions["correctness"] = max(dimensions["correctness"], 800)
        dimensions["reproducibility"] = max(dimensions["reproducibility"], 800)
    if row.state == "REFUTED":
        dimensions["correctness"] = 0
    if row.rights_status == "unknown":
        dimensions["reproducibility"] = min(dimensions["reproducibility"], 300)
    return dimensions


def _largest_remainder(total: int, weights: dict[str, int]) -> dict[str, int]:
    if not weights or sum(weights.values()) <= 0:
        return {}
    denominator = sum(weights.values())
    base = {key: (total * weight) // denominator for key, weight in weights.items()}
    left = total - sum(base.values())
    order = sorted(weights, key=lambda key: (-(total * weights[key] % denominator), key))
    for key in order[:left]:
        base[key] += 1
    return base


async def calculate_reward(
    session: AsyncSession, *, candidate_id: str, agent_id: str, total_aceros: int,
    trace_id: str | None
) -> ResearchRewardCalculation:
    if type(total_aceros) is not int or not 100 <= total_aceros <= 1_000_000_000_000:
        raise ValidationFailed("total_aceros must be an integer between 100 and 1000000000000.")
    if total_aceros % 100:
        raise ValidationFailed("total_aceros must be divisible by 100 for exact allocation.")
    candidate = await session.get(ResearchCandidateSnapshot, candidate_id, with_for_update=True)
    if candidate is None:
        raise NotFound("Research candidate not found.")
    if candidate.created_by_agent_id != agent_id:
        raise OwnerAuthorityRequired("Only the candidate creator may calculate its reward.")
    existing = (
        await session.execute(
            select(ResearchRewardCalculation).where(
                ResearchRewardCalculation.candidate_id == candidate_id,
                ResearchRewardCalculation.algorithm_version == SCORING_VERSION,
            )
        )
    ).scalar_one_or_none()
    if existing:
        if existing.total_aceros != total_aceros:
            raise Conflict("Reward amount differs from the existing calculation.")
        return existing
    mission = await session.get(Mission, candidate.challenge_id)
    submission = await session.get(MissionChallengeSubmission, candidate.submission_id)
    assert mission is not None and submission is not None
    objects, edges, current_root = await _knowledge_material(session, candidate.challenge_id)
    if current_root != candidate.knowledge_root_hash:
        raise Conflict(
            "Knowledge graph changed; freeze a new candidate version before reward calculation."
        )
    inbound: dict[str, int] = defaultdict(int)
    validation: dict[str, int] = defaultdict(int)
    for edge in edges:
        inbound[edge.target_object_id] += 1
        if edge.relation_type in {"replicates", "reviews", "supports"}:
            validation[edge.target_object_id] += 1
    actor_weights: dict[str, int] = defaultdict(int)
    score_rows = []
    for obj in objects:
        dimensions = _dimensions_for(obj, inbound[obj.object_id], validation[obj.object_id])
        weighted = sum(dimensions[name] * WEIGHTS_BPS[name] for name in WEIGHTS_BPS) // 10000
        explanation = {
            "object_type": obj.object_type,
            "state": obj.state,
            "inbound_dependencies": inbound[obj.object_id],
            "validation_edges": validation[obj.object_id],
            "weights_bps": WEIGHTS_BPS,
            "messages_votes_presence_rewarded": False,
        }
        input_hash = canonical_json_hash(
            {
                "object_hash": obj.canonical_content_hash,
                "dimensions": dimensions,
                "explanation": explanation,
            },
            domain="agora.research.score.input.v1",
        )
        score = ResearchContributionScore(
            score_id=new_research_score_id(),
            challenge_id=candidate.challenge_id,
            candidate_id=candidate_id,
            object_id=obj.object_id,
            author_agent_id=obj.author_agent_id,
            algorithm_version=SCORING_VERSION,
            dimensions=dimensions,
            weighted_score=weighted,
            explanation=explanation,
            input_hash=input_hash,
            created_at=now_utc(),
        )
        session.add(score)
        score_rows.append(score)
        if weighted > 0:
            actor_weights[obj.author_agent_id] += weighted
    pools = {name: total_aceros * percent // 100 for name, percent in REWARD_PERCENT.items()}
    final_authors = sorted(set(submission.team_agent_ids or [submission.agent_id]))
    final_alloc = _largest_remainder(pools["final_solution"], {actor: 1 for actor in final_authors})
    participant_alloc = _largest_remainder(
        pools["participant_contribution_pool"], dict(actor_weights)
    )
    reviews = list(
        (
            await session.execute(
                select(InstitutionalReview).where(InstitutionalReview.candidate_id == candidate_id)
            )
        ).scalars()
    )
    institution_ids = sorted({row.institution_id for row in reviews})
    institution_alloc = _largest_remainder(
        pools["institutional_validation_pool"],
        {institution_id: 1 for institution_id in institution_ids},
    )
    allocation = {
        "pools": pools,
        "research_proposer": [
            {
                "actor_type": "agent",
                "actor_id": mission.created_by_agent_id,
                "amount_aceros": pools["research_proposer"],
            }
        ],
        "final_solution": [
            {"actor_type": "agent", "actor_id": key, "amount_aceros": value}
            for key, value in final_alloc.items()
        ],
        "participant_contribution_pool": [
            {
                "actor_type": "agent",
                "actor_id": key,
                "amount_aceros": value,
                "score": actor_weights[key],
            }
            for key, value in participant_alloc.items()
        ],
        "institutional_validation_pool": [
            {"actor_type": "institution", "actor_id": key, "amount_aceros": value}
            for key, value in institution_alloc.items()
        ],
        "agora_infrastructure": [
            {
                "actor_type": "protocol",
                "actor_id": "AGORA_INFRASTRUCTURE_TREASURY",
                "amount_aceros": pools["agora_infrastructure"],
            }
        ],
        "reserved_unallocated": {
            "participant_contribution_pool": pools["participant_contribution_pool"]
            - sum(participant_alloc.values()),
            "institutional_validation_pool": pools["institutional_validation_pool"]
            - sum(institution_alloc.values()),
        },
    }
    body = {
        "candidate_hash": candidate.content_hash,
        "algorithm_version": SCORING_VERSION,
        "total_aceros": total_aceros,
        "allocation": allocation,
        "genealogy_hash": current_root,
    }
    row = ResearchRewardCalculation(
        reward_id=new_research_reward_id(),
        challenge_id=candidate.challenge_id,
        candidate_id=candidate_id,
        algorithm_version=SCORING_VERSION,
        total_aceros=total_aceros,
        allocation=allocation,
        genealogy_hash=current_root,
        state="PROVISIONAL",
        explanation={
            "policy": REWARD_PERCENT,
            "weights_bps": WEIGHTS_BPS,
            "institutional_pool_rewards_review_work_not_positive_vote": True,
            "consensus_is_not_truth": True,
        },
        content_hash=canonical_json_hash(body, domain="agora.research.reward.v1"),
        created_at=now_utc(),
    )
    session.add(row)
    await session.flush()
    await append_event(
        session,
        event_type="reward.calculated",
        actor={"agent_id": SYSTEM_ACTOR_ID},
        payload={
            "reward_id": row.reward_id,
            "candidate_id": candidate_id,
            "content_hash": row.content_hash,
            "state": row.state,
        },
        trace_id=trace_id,
    )
    return row


async def lock_reward(
    session: AsyncSession, *, candidate_id: str, trace_id: str | None
) -> ResearchRewardCalculation:
    settings = get_settings()
    if settings.is_production or not settings.institutional_registry_control_plane_enabled:
        raise OwnerAuthorityRequired("Institutional reward control plane is disabled.")
    candidate = await session.get(ResearchCandidateSnapshot, candidate_id, with_for_update=True)
    if candidate is None:
        raise NotFound("Research candidate not found.")
    reward = (
        await session.execute(
            select(ResearchRewardCalculation)
            .where(ResearchRewardCalculation.candidate_id == candidate_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if reward is None:
        raise Conflict("Calculate a provisional reward before locking it.")
    if reward.state in {"LOCKED", "PAYOUT_READY", "SETTLED"}:
        return reward
    reviews = list(
        (
            await session.execute(
                select(InstitutionalReview, ResearchInstitution)
                .join(
                    ResearchInstitution,
                    ResearchInstitution.institution_id == InstitutionalReview.institution_id,
                )
                .where(InstitutionalReview.candidate_id == candidate_id)
            )
        ).all()
    )
    if any(review.verdict in ADVERSE_VERDICTS for review, _ in reviews):
        raise Conflict(
            "Current candidate has an adverse institutional verdict; create a new version."
        )
    approved_legal_entities = {
        institution.legal_entity_id
        for review, institution in reviews
        if review.verdict in APPROVAL_VERDICTS and institution.state == "ACTIVE"
    }
    if len(approved_legal_entities) < 2:
        raise Conflict(
            "Two independent active institutions must approve the exact candidate version."
        )
    _, _, root = await _knowledge_material(session, candidate.challenge_id)
    if root != candidate.knowledge_root_hash or root != reward.genealogy_hash:
        raise Conflict("Knowledge genealogy integrity changed after candidate freeze.")
    challenge_candidate_ids = list(
        (
            await session.execute(
                select(ResearchCandidateSnapshot.candidate_id).where(
                    ResearchCandidateSnapshot.challenge_id == candidate.challenge_id
                )
            )
        ).scalars()
    )
    all_review_work = list(
        (
            await session.execute(
                select(InstitutionalReview, ResearchInstitution)
                .join(
                    ResearchInstitution,
                    ResearchInstitution.institution_id == InstitutionalReview.institution_id,
                )
                .where(InstitutionalReview.candidate_id.in_(challenge_candidate_ids))
            )
        ).all()
    )
    institution_work_units: dict[str, int] = defaultdict(int)
    for _review, institution in all_review_work:
        if institution.state == "ACTIVE":
            institution_work_units[institution.institution_id] += 1
    institutional_pool = int(reward.allocation["pools"]["institutional_validation_pool"])
    institution_alloc = _largest_remainder(institutional_pool, institution_work_units)
    provisional_hash = reward.content_hash
    reward.allocation = {
        **reward.allocation,
        "institutional_validation_pool": [
            {
                "actor_type": "institution",
                "actor_id": institution_id,
                "amount_aceros": amount,
                "review_work_units": institution_work_units[institution_id],
            }
            for institution_id, amount in institution_alloc.items()
        ],
        "reserved_unallocated": {
            **reward.allocation["reserved_unallocated"],
            "institutional_validation_pool": 0,
        },
    }
    reward.explanation = {
        **reward.explanation,
        "provisional_content_hash": provisional_hash,
        "finalized_institution_ids": sorted(institution_work_units),
        "institutional_work_includes_adverse_prior_versions": True,
    }
    reward.content_hash = canonical_json_hash(
        {
            "candidate_hash": candidate.content_hash,
            "algorithm_version": reward.algorithm_version,
            "total_aceros": reward.total_aceros,
            "allocation": reward.allocation,
            "genealogy_hash": reward.genealogy_hash,
            "provisional_content_hash": provisional_hash,
        },
        domain="agora.research.reward.locked.v1",
    )
    reward.state = "LOCKED"
    reward.locked_at = now_utc()
    candidate.state = "HUMAN_VALIDATED"
    await append_event(
        session,
        event_type="research.human_validated",
        actor={"agent_id": SYSTEM_ACTOR_ID},
        payload={
            "candidate_id": candidate_id,
            "institution_count": len(approved_legal_entities),
        },
        trace_id=trace_id,
    )
    await append_event(
        session,
        event_type="reward.locked",
        actor={"agent_id": SYSTEM_ACTOR_ID},
        payload={
            "reward_id": reward.reward_id,
            "candidate_id": candidate_id,
            "amount_aceros": reward.total_aceros,
            "provisional_content_hash": provisional_hash,
            "locked_content_hash": reward.content_hash,
        },
        trace_id=trace_id,
    )
    return reward


async def generate_publication_package(
    session: AsyncSession, *, candidate_id: str, trace_id: str | None
) -> ResearchPublicationPackage:
    candidate = await session.get(ResearchCandidateSnapshot, candidate_id)
    if candidate is None:
        raise NotFound("Research candidate not found.")
    reward = (
        await session.execute(
            select(ResearchRewardCalculation).where(
                ResearchRewardCalculation.candidate_id == candidate_id
            )
        )
    ).scalar_one_or_none()
    if candidate.state != "HUMAN_VALIDATED" or reward is None or reward.state != "LOCKED":
        raise Conflict("Publication preparation requires human validation and a locked reward.")
    existing = (
        await session.execute(
            select(ResearchPublicationPackage).where(
                ResearchPublicationPackage.candidate_id == candidate_id
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    reviews = list(
        (
            await session.execute(
                select(InstitutionalReview)
                .where(InstitutionalReview.candidate_id == candidate_id)
                .order_by(InstitutionalReview.created_at)
            )
        ).scalars()
    )
    objects, edges, root = await _knowledge_material(session, candidate.challenge_id)
    provenance = {
        "label": "Powered by AGORA",
        "agora_role": (
            "Research coordination, agentic computation, provenance and knowledge "
            "genealogy infrastructure"
        ),
        "human_responsibility_required": True,
        "candidate": _candidate_view(candidate),
        "knowledge_root_hash": root,
        "knowledge_objects": [
            {
                "object_id": row.object_id,
                "type": row.object_type,
                "hash": row.canonical_content_hash,
                "author_agent_id": row.author_agent_id,
                "state": row.state,
                "created_at": row.created_at.isoformat(),
            }
            for row in objects
        ],
        "knowledge_edges": [
            {
                "edge_id": row.edge_id,
                "source": row.source_object_id,
                "target": row.target_object_id,
                "relation": row.relation_type,
                "hash": row.canonical_content_hash,
            }
            for row in edges
        ],
        "institutional_reviews": [
            {
                "review_id": row.review_id,
                "institution_id": row.institution_id,
                "verdict": row.verdict,
                "review_hash": row.content_hash,
            }
            for row in reviews
        ],
        "reward": {
            "reward_id": reward.reward_id,
            "algorithm_version": reward.algorithm_version,
            "allocation": reward.allocation,
            "content_hash": reward.content_hash,
        },
    }
    package_hash = canonical_json_hash(provenance, domain="agora.research.publication.package.v1")
    row = ResearchPublicationPackage(
        package_id=new_research_publication_package_id(),
        challenge_id=candidate.challenge_id,
        candidate_id=candidate_id,
        manuscript_artifact_version_id=candidate.manuscript_artifact_version_id,
        responsible_institution_ids=sorted(
            {review.institution_id for review in reviews if review.verdict in APPROVAL_VERDICTS}
        ),
        provenance=provenance,
        package_hash=package_hash,
        state="PREPARED",
        created_at=now_utc(),
    )
    session.add(row)
    await session.flush()
    await append_event(
        session,
        event_type="publication.package.generated",
        actor={"agent_id": SYSTEM_ACTOR_ID},
        payload={
            "package_id": row.package_id,
            "candidate_id": candidate_id,
            "package_hash": package_hash,
        },
        trace_id=trace_id,
    )
    return row


async def challenge_research_view(session: AsyncSession, challenge_id: str) -> dict[str, Any]:
    mission = await session.get(Mission, challenge_id)
    if mission is None:
        raise NotFound("Research challenge not found.")
    objects, edges, root = await _knowledge_material(session, challenge_id)
    candidates = list(
        (
            await session.execute(
                select(ResearchCandidateSnapshot)
                .where(ResearchCandidateSnapshot.challenge_id == challenge_id)
                .order_by(ResearchCandidateSnapshot.candidate_version)
            )
        ).scalars()
    )
    candidate_ids = [row.candidate_id for row in candidates]
    reviews = (
        list(
            (
                await session.execute(
                    select(InstitutionalReview)
                    .where(InstitutionalReview.candidate_id.in_(candidate_ids))
                    .order_by(InstitutionalReview.created_at)
                )
            ).scalars()
        )
        if candidate_ids
        else []
    )
    rewards = list(
        (
            await session.execute(
                select(ResearchRewardCalculation).where(
                    ResearchRewardCalculation.challenge_id == challenge_id
                )
            )
        ).scalars()
    )
    packages = list(
        (
            await session.execute(
                select(ResearchPublicationPackage).where(
                    ResearchPublicationPackage.challenge_id == challenge_id
                )
            )
        ).scalars()
    )
    from agora_api.institutional_validator_service import panel_view

    validator_panels = [await panel_view(session, row.candidate_id) for row in candidates]
    return {
        "protocol_version": PROTOCOL_VERSION,
        "challenge": {
            "challenge_id": mission.mission_id,
            "title": mission.title,
            "objective": mission.objective,
            "state": mission.state,
            "consensus_is_truth": False,
        },
        "genealogy": {
            "root_hash": root,
            "nodes": [
                {
                    "node_id": row.object_id,
                    "node_type": row.object_type,
                    "author_actor_id": row.author_agent_id,
                    "content_hash": row.canonical_content_hash,
                    "status": row.state,
                    "created_at": row.created_at.isoformat(),
                    "summary": row.public_summary,
                }
                for row in objects
            ],
            "edges": [
                {
                    "edge_id": row.edge_id,
                    "source": row.source_object_id,
                    "target": row.target_object_id,
                    "relation": row.relation_type,
                }
                for row in edges
            ],
        },
        "candidates": [_candidate_view(row) for row in candidates],
        "institutional_reviews": [
            {
                "review_id": row.review_id,
                "candidate_id": row.candidate_id,
                "institution_id": row.institution_id,
                "verdict": row.verdict,
                "content_hash": row.content_hash,
                "created_at": row.created_at.isoformat(),
            }
            for row in reviews
        ],
        "institutional_validator_layer": {
            "actor_type": "INSTITUTIONAL_VALIDATOR",
            "pilot_is_synthetic": True,
            "pilot_can_satisfy_human_validation": False,
            "pilot_can_release_tokoin": False,
            "panels": validator_panels,
        },
        "rewards": [
            {
                "reward_id": row.reward_id,
                "candidate_id": row.candidate_id,
                "state": row.state,
                "total_aceros": row.total_aceros,
                "allocation": row.allocation,
                "algorithm_version": row.algorithm_version,
                "content_hash": row.content_hash,
            }
            for row in rewards
        ],
        "publication_packages": [
            {
                "package_id": row.package_id,
                "candidate_id": row.candidate_id,
                "state": row.state,
                "package_hash": row.package_hash,
                "responsible_institution_ids": row.responsible_institution_ids,
            }
            for row in packages
        ],
    }


async def reproducibility_package(session: AsyncSession, candidate_id: str) -> dict[str, Any]:
    """Export exact public preimages; fail closed on drift or unavailable history."""
    from sqlalchemy import or_

    from agora_api.research_export import verify_package

    candidate = await session.get(ResearchCandidateSnapshot, candidate_id)
    if candidate is None:
        raise NotFound("Research candidate not found.")
    objects = list((await session.execute(select(MagnaKnowledgeObject).where(
        MagnaKnowledgeObject.challenge_id == candidate.challenge_id,
        MagnaKnowledgeObject.created_at <= candidate.created_at,
    ).order_by(MagnaKnowledgeObject.created_at, MagnaKnowledgeObject.object_id)
        .limit(5001))).scalars())
    if len(objects) > 5000:
        raise Conflict("Candidate graph exceeds the bounded export limit.")
    if any(row.visibility_lane != "OPEN" for row in objects):
        raise OwnerAuthorityRequired("Public export cannot disclose non-OPEN genealogy material.")
    object_map = {row.object_id: row for row in objects}
    edges = list((await session.execute(select(MagnaKnowledgeEdge).where(
        MagnaKnowledgeEdge.source_object_id.in_(object_map),
        MagnaKnowledgeEdge.target_object_id.in_(object_map),
        MagnaKnowledgeEdge.created_at <= candidate.created_at,
        or_(MagnaKnowledgeEdge.retracted_at.is_(None),
            MagnaKnowledgeEdge.retracted_at > candidate.created_at),
    ).order_by(MagnaKnowledgeEdge.created_at, MagnaKnowledgeEdge.edge_id).limit(10001))).scalars())
    if len(edges) > 10000:
        raise Conflict("Candidate graph exceeds the bounded export limit.")
    solution = object_map.get(candidate.final_solution_object_id)
    if solution is None:
        raise Conflict("Frozen final solution bytes are unavailable.")
    body = {
        "challenge_id": candidate.challenge_id,
        "submission_id": candidate.submission_id,
        "candidate_version": candidate.candidate_version,
        "final_solution_hash": solution.canonical_content_hash,
        "manuscript_artifact_version_id": candidate.manuscript_artifact_version_id,
        "knowledge_root_hash": candidate.knowledge_root_hash,
        "consensus_snapshot": candidate.consensus_snapshot,
        "protocol_version": candidate.protocol_version,
    }
    package = {
        "schema": "agora.reproducibility-package.v1",
        "candidate": {"candidate_id": candidate.candidate_id,
                      "final_solution_object_id": candidate.final_solution_object_id,
                      "content_hash": candidate.content_hash, "canonical_payload": body},
        "objects": [{"object_id": row.object_id, "content_hash": row.canonical_content_hash,
                     "canonical_payload": {
                         "object_type": row.object_type, "payload": row.payload,
                         "parents": row.parent_hashes, "lane": row.visibility_lane,
                         "rights": row.rights_status, "license_id": row.license_id,
                         "constitution_hash": row.constitution_hash,
                     }} for row in objects],
        "edges": [{"edge_id": row.edge_id, "source_object_id": row.source_object_id,
                   "target_object_id": row.target_object_id,
                   "content_hash": row.canonical_content_hash, "canonical_payload": {
                       "source": object_map[row.source_object_id].canonical_content_hash,
                       "target": object_map[row.target_object_id].canonical_content_hash,
                       "relation_type": row.relation_type, "payload": row.payload,
                   }} for row in edges],
        "limits": {"authenticity_requires_trusted_candidate_hash": True,
                   "execution_attested": False, "scientific_truth_attested": False,
                   "artifact_bytes_included": False},
    }
    try:
        package["verification"] = verify_package(package, candidate.content_hash)
    except (ValueError, KeyError, TypeError) as exc:
        raise Conflict("Frozen canonical material cannot be reconstructed exactly.") from exc
    return package
