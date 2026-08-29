"""MAGNA Sprint 02 Research Allocation Center.

This service extends the existing formal market. It uses only TEST research
credits, never TOKOIN, and every remote/public text remains untrusted data.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.boundary import validate_boundary
from agora_api.config import get_settings
from agora_api.errors import Conflict, NotFound, ValidationFailed
from agora_api.events import append_event, now_utc
from agora_api.ids import (
    new_commitment_id,
    new_contribution_pool_id,
    new_duplicate_link_id,
    new_eligibility_review_id,
    new_priority_assessment_id,
    new_research_appeal_id,
    new_research_proposal_id,
    new_research_reservation_id,
)
from agora_api.magna_constitution import (
    EPOCH_SECONDS,
    RELEASE_POLICY_VERSION,
    current_charter,
    current_constitution,
    evaluate_rules,
    release_policy_view,
)
from agora_api.models import (
    Agent,
    ContributionPool,
    EligibilityReview,
    PriorityAssessment,
    ResearchAppeal,
    ResearchCommitment,
    ResearchCreditReservation,
    ResearchDuplicateLink,
    ResearchProposal,
    ResearchReleaseEpoch,
)
from agora_api.provenance import SYSTEM_ACTOR_ID, add_provenance, world_instance_for_class

RESEARCH_MARKET_VERSION = "research-allocation-market.v1"
RESEARCH_CREDIT_ASSET = "RESEARCH_CREDITS_TEST"
RESEARCH_CREDIT_AMOUNT = 100_000_000
SCHEDULER_ENABLED = False
CLAIM_WINDOW_SECONDS = 300
POLICY_VERSION = "research-priority-policy.v1"

WEIGHTS = {
    "expected_human_value": 20,
    "novelty_and_nonduplication": 15,
    "tractability": 15,
    "evidence_and_data_availability": 10,
    "reproducibility": 15,
    "resource_efficiency": 10,
    "safety_and_externalities": 10,
    "transfer_or_usefulness_potential": 5,
}
FORBIDDEN_POSITIVE_SIGNALS = {
    "message_count",
    "movement_count",
    "presence_duration",
    "popularity",
    "wealth",
    "tokoin_balance",
    "obedience",
}


def canonical_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _event_payload(row: ResearchProposal) -> dict[str, Any]:
    return {
        "proposal_id": row.proposal_id,
        "world_id": row.world_id,
        "state": row.state,
        "content_hash": row.content_hash,
        "market_class": "test",
    }


async def _event(
    session: AsyncSession,
    event_type: str,
    actor_id: str,
    payload: dict[str, Any],
    trace_id: str | None,
) -> str:
    event = await append_event(
        session,
        event_type=event_type,
        actor={"agent_id": actor_id},
        payload=payload,
        trace_id=trace_id,
        provenance_class="test",
        provenance_world_instance_id=world_instance_for_class("test"),
    )
    return event.event_id


async def _provenance(session: AsyncSession, table: str, record_id: str, actor_id: str) -> None:
    await add_provenance(
        session,
        record_table=table,
        record_id=record_id,
        provenance_class="test",
        world_instance_id=world_instance_for_class("test"),
        created_by="magna-research-market-v1",
        created_by_actor_id=actor_id,
        created_by_actor_provenance="test",
        source_reference=RESEARCH_MARKET_VERSION,
    )


async def require_market_rules(session: AsyncSession, world_id: str) -> tuple[str, str, str]:
    constitution = await current_constitution(session)
    charter = await current_charter(session, world_id)
    if charter.sunset_at and charter.sunset_at <= now_utc():
        raise Conflict("MAGNA charter is expired; research market fails closed.")
    return constitution.content_hash, charter.content_hash, constitution.world_instance_id


def _gate_reasons(payload: dict[str, Any]) -> list[str]:
    body = payload["proposal"]
    reasons: list[str] = []
    for field in (
        "human_value",
        "prior_evidence",
        "falsification_condition",
        "method",
        "rights_status",
        "closure_criteria",
    ):
        if len(str(body.get(field, "")).strip()) < 12:
            reasons.append(f"needs_information:{field}")
    risk = payload["risk_level"]
    if risk == "UNCLASSIFIED":
        reasons.append("risk_unclassified")
    if risk in {"D2", "D3"}:
        reasons.append("needs_human_authority:risk_level")
    text_blob = " ".join(
        str(body.get(key, ""))
        for key in ("question", "objective", "method", "risks", "rights_status")
    ).lower()
    if any(
        marker in text_blob for marker in ("biomedical", "wet-lab", "clinical", "human subject")
    ):
        reasons.append("needs_human_authority:human_or_biomedical")
    if any(marker in text_blob for marker in ("exploit", "malware", "credential theft")):
        reasons.append("needs_human_authority:offensive_security")
    if any(
        marker in text_blob for marker in ("shell.execute", "secrets.read", "localpolicyengine")
    ):
        reasons.append("remote_content_untrusted_no_local_permission")
    return sorted(set(reasons))


def deterministic_gate_decision(payload: dict[str, Any]) -> tuple[str, list[str]]:
    reasons = _gate_reasons(payload)
    if any(reason.startswith("needs_human_authority") for reason in reasons):
        return "NEEDS_HUMAN_AUTHORITY", reasons
    if any(reason.startswith(("needs_information", "risk_unclassified")) for reason in reasons):
        return "NEEDS_INFORMATION", reasons
    return "PASS", ["hard_gates_passed"]


def proposal_view(row: ResearchProposal) -> dict[str, Any]:
    return {
        "proposal_id": row.proposal_id,
        "world_instance_id": row.world_instance_id,
        "world_id": row.world_id,
        "title": row.title,
        "question": row.question,
        "objective": row.objective,
        "state": row.state,
        "content_hash": row.content_hash,
        "beneficial_controller_id": row.beneficial_controller_id,
        "risk_level": row.risk_level,
        "constitution_hash": row.constitution_hash,
        "charter_hash": row.charter_hash,
        "rule_evaluation_receipt_id": row.rule_evaluation_receipt_id,
        "created_by_agent_id": row.created_by_agent_id,
        "eligible_at": iso(row.eligible_at),
        "released_at": iso(row.released_at),
        "revision": row.revision,
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
        "trust": {
            "classification": "public_world_context",
            "instruction_trust": "untrusted_remote",
            "does_not_grant_local_permissions": True,
            "does_not_assert_truth": True,
        },
        "next_allowed_actions": next_allowed_actions(row.state),
    }


def next_allowed_actions(state: str) -> list[str]:
    return {
        "PROPOSED": ["submit_for_eligibility", "withdraw", "appeal"],
        "ELIGIBILITY_REVIEW": ["eligibility_review", "appeal"],
        "NEEDS_INFORMATION": ["provide_information", "appeal"],
        "NEEDS_HUMAN_AUTHORITY": ["appeal", "withdraw"],
        "ELIGIBLE": ["join", "commit_resource", "create_pool", "wait_for_epoch"],
        "RELEASED_ACTIVE": ["join", "commit_resource", "pause", "signal_dormant", "appeal"],
        "DORMANT": ["reopen", "appeal"],
        "CLOSED_NONVIABLE": ["appeal"],
        "CLOSED_SAFETY": ["human_authority_required"],
        "WITHDRAWN": ["inspect"],
    }.get(state, ["inspect"])


async def _get_proposal(session: AsyncSession, proposal_id: str) -> ResearchProposal:
    row = await session.get(ResearchProposal, proposal_id)
    if row is None:
        raise NotFound("Research proposal not found.")
    return row


async def create_research_proposal(
    session: AsyncSession,
    *,
    agent: Agent,
    payload: dict[str, Any],
    trace_id: str | None,
) -> ResearchProposal:
    validate_boundary(
        "research-market.schema.json", "/$defs/CreateResearchProposalRequest", payload
    )
    constitution_hash, charter_hash, world_instance_id = await require_market_rules(
        session, payload["world_id"]
    )
    existing = (
        await session.execute(
            select(ResearchProposal).where(
                ResearchProposal.created_by_agent_id == agent.agent_id,
                ResearchProposal.idempotency_key == payload["idempotency_key"],
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    body_hash = canonical_hash(payload)
    decision, reasons = deterministic_gate_decision(payload)
    rule_result = await evaluate_rules(
        session,
        device=None,
        payload={
            "world_instance_id": world_instance_id,
            "current_constitution_hash": constitution_hash,
            "current_charter_hash": charter_hash,
            "world_id": payload["world_id"],
            "requested_action": "research.propose",
            "resource_context": {"requested_capabilities": []},
            "challenge_or_commitment_context": None,
            "as_of": now_utc().isoformat().replace("+00:00", "Z"),
        },
    )
    if rule_result["decision"] != "allow":
        raise Conflict("Effective MAGNA rules do not allow research proposal creation.")
    ts = now_utc()
    row = ResearchProposal(
        proposal_id=new_research_proposal_id(),
        idempotency_key=payload["idempotency_key"],
        world_instance_id=world_instance_id,
        world_id=payload["world_id"],
        title=payload["title"],
        question=payload["proposal"]["question"],
        objective=payload["proposal"]["objective"],
        state="PROPOSED" if decision == "PASS" else decision,
        content_hash=body_hash,
        proposal_body=payload["proposal"],
        beneficial_controller_id=payload["beneficial_controller_id"],
        risk_level=payload["risk_level"],
        constitution_hash=constitution_hash,
        charter_hash=charter_hash,
        rule_evaluation_receipt_id=rule_result["decision_receipt_id"],
        created_by_agent_id=agent.agent_id,
        created_by_agent_version_id=agent.current_version_id,
        created_at=ts,
        updated_at=ts,
    )
    session.add(row)
    await session.flush()
    await _provenance(session, "research_proposals", row.proposal_id, agent.agent_id)
    await _event(
        session, "research.proposal.created", agent.agent_id, _event_payload(row), trace_id
    )
    return row


async def submit_for_eligibility(
    session: AsyncSession, *, proposal_id: str, agent: Agent, trace_id: str | None
) -> ResearchProposal:
    row = await _get_proposal(session, proposal_id)
    if row.created_by_agent_id != agent.agent_id:
        raise Conflict("Only the proposing agent may submit this proposal.")
    await require_market_rules(session, row.world_id)
    if row.state == "PROPOSED":
        row.state = "ELIGIBILITY_REVIEW"
        row.updated_at = now_utc()
        await _event(
            session,
            "research.proposal.submitted_for_eligibility",
            agent.agent_id,
            _event_payload(row),
            trace_id,
        )
    return row


async def review_eligibility(
    session: AsyncSession,
    *,
    proposal_id: str,
    agent: Agent,
    payload: dict[str, Any],
    trace_id: str | None,
) -> EligibilityReview:
    validate_boundary("research-market.schema.json", "/$defs/EligibilityReviewRequest", payload)
    proposal = await _get_proposal(session, proposal_id)
    await require_market_rules(session, proposal.world_id)
    existing = (
        await session.execute(
            select(EligibilityReview).where(
                EligibilityReview.reviewer_agent_id == agent.agent_id,
                EligibilityReview.idempotency_key == payload["idempotency_key"],
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    deterministic_decision, deterministic_reasons = deterministic_gate_decision(
        {
            "risk_level": proposal.risk_level,
            "proposal": proposal.proposal_body,
        }
    )
    decision = payload["decision"]
    if deterministic_decision != "PASS" and decision == "PASS":
        raise ValidationFailed("A hard gate failure cannot be overridden by a positive review.")
    reasons = sorted(set(payload["reason_codes"]) | set(deterministic_reasons))
    ts = now_utc()
    review = EligibilityReview(
        review_id=new_eligibility_review_id(),
        proposal_id=proposal_id,
        idempotency_key=payload["idempotency_key"],
        reviewer_agent_id=agent.agent_id,
        decision=decision,
        reason_codes=reasons,
        gate_results={
            "deterministic_decision": deterministic_decision,
            "human_authority_receipt_hash": payload.get("human_authority_receipt_hash"),
        },
        created_at=ts,
    )
    session.add(review)
    if decision == "PASS":
        proposal.state = "ELIGIBLE"
        proposal.eligible_at = ts
        event_type = "research.proposal.eligible"
    else:
        proposal.state = decision
        event_type = "research.eligibility.reviewed"
    proposal.updated_at = ts
    await _event(
        session,
        event_type,
        agent.agent_id,
        {"review_id": review.review_id, **_event_payload(proposal), "reason_codes": reasons},
        trace_id,
    )
    return review


def portfolio_score(vector: dict[str, int], uncertainty: int) -> int:
    score = sum(vector[key] * weight for key, weight in WEIGHTS.items()) // 100
    return max(0, score - uncertainty // 5)


async def create_priority_assessment(
    session: AsyncSession,
    *,
    proposal_id: str,
    agent: Agent,
    payload: dict[str, Any],
    trace_id: str | None,
) -> PriorityAssessment:
    validate_boundary("research-market.schema.json", "/$defs/PriorityAssessmentRequest", payload)
    proposal = await _get_proposal(session, proposal_id)
    await require_market_rules(session, proposal.world_id)
    if proposal.state not in {"ELIGIBILITY_REVIEW", "ELIGIBLE", "RELEASED_ACTIVE"}:
        raise Conflict("Priority assessment requires an active review or eligible proposal.")
    if FORBIDDEN_POSITIVE_SIGNALS & set(payload["vector"]):
        raise ValidationFailed("Social activity and wealth cannot be positive ranking signals.")
    existing = (
        await session.execute(
            select(PriorityAssessment).where(
                PriorityAssessment.assessor_agent_id == agent.agent_id,
                PriorityAssessment.idempotency_key == payload["idempotency_key"],
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    score = portfolio_score(payload["vector"], payload["uncertainty"])
    assessment = PriorityAssessment(
        assessment_id=new_priority_assessment_id(),
        proposal_id=proposal_id,
        idempotency_key=payload["idempotency_key"],
        assessor_agent_id=agent.agent_id,
        policy_version=POLICY_VERSION,
        input_hash=canonical_hash({"proposal_hash": proposal.content_hash, **payload}),
        vector=payload["vector"],
        uncertainty=payload["uncertainty"],
        pareto_layer=1,
        portfolio_score=score,
        reason_codes=["vector_preserved", "not_truth_score", "pareto_layer_visible"],
        created_at=now_utc(),
    )
    session.add(assessment)
    await _event(
        session,
        "research.assessment.created",
        agent.agent_id,
        {
            "assessment_id": assessment.assessment_id,
            "proposal_id": proposal_id,
            "policy_version": POLICY_VERSION,
            "portfolio_score": score,
            "not_truth_score": True,
        },
        trace_id,
    )
    return assessment


async def create_commitment(
    session: AsyncSession,
    *,
    proposal_id: str,
    agent: Agent,
    payload: dict[str, Any],
    trace_id: str | None,
) -> ResearchCommitment:
    validate_boundary("research-market.schema.json", "/$defs/CommitmentRequest", payload)
    proposal = await _get_proposal(session, proposal_id)
    if proposal.state not in {"ELIGIBLE", "RELEASED_ACTIVE"}:
        raise Conflict("Commitments require an eligible or released candidate.")
    existing = (
        await session.execute(
            select(ResearchCommitment).where(
                ResearchCommitment.agent_id == agent.agent_id,
                ResearchCommitment.idempotency_key == payload["idempotency_key"],
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    ts = now_utc()
    row = ResearchCommitment(
        commitment_id=new_commitment_id(),
        proposal_id=proposal_id,
        idempotency_key=payload["idempotency_key"],
        agent_id=agent.agent_id,
        beneficial_controller_id=payload["beneficial_controller_id"],
        role=payload["role"],
        resource_limits=payload["resource_limits"],
        state="active",
        expires_at=parse_dt(payload.get("expires_at")),
        created_at=ts,
        updated_at=ts,
    )
    session.add(row)
    await _event(
        session,
        "research.commitment.created",
        agent.agent_id,
        {"commitment_id": row.commitment_id, "proposal_id": proposal_id, "role": row.role},
        trace_id,
    )
    return row


async def create_pool(
    session: AsyncSession,
    *,
    proposal_id: str,
    agent: Agent,
    payload: dict[str, Any],
    trace_id: str | None,
) -> ContributionPool:
    validate_boundary("research-market.schema.json", "/$defs/ContributionPoolRequest", payload)
    await _get_proposal(session, proposal_id)
    existing = (
        await session.execute(
            select(ContributionPool).where(
                ContributionPool.created_by_agent_id == agent.agent_id,
                ContributionPool.idempotency_key == payload["idempotency_key"],
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    row = ContributionPool(
        pool_id=new_contribution_pool_id(),
        proposal_id=proposal_id,
        idempotency_key=payload["idempotency_key"],
        created_by_agent_id=agent.agent_id,
        terms=payload["terms"] | {"settlement_executed": False, "asset": RESEARCH_CREDIT_ASSET},
        state="open",
        created_at=now_utc(),
    )
    session.add(row)
    await _event(
        session,
        "research.pool.created",
        agent.agent_id,
        {"pool_id": row.pool_id, "proposal_id": proposal_id, "settlement_executed": False},
        trace_id,
    )
    return row


async def create_appeal(
    session: AsyncSession,
    *,
    proposal_id: str,
    agent: Agent,
    payload: dict[str, Any],
    trace_id: str | None,
) -> ResearchAppeal:
    validate_boundary("research-market.schema.json", "/$defs/AppealRequest", payload)
    await _get_proposal(session, proposal_id)
    existing = (
        await session.execute(
            select(ResearchAppeal).where(
                ResearchAppeal.created_by_agent_id == agent.agent_id,
                ResearchAppeal.idempotency_key == payload["idempotency_key"],
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    appeal = ResearchAppeal(
        appeal_id=new_research_appeal_id(),
        proposal_id=proposal_id,
        idempotency_key=payload["idempotency_key"],
        created_by_agent_id=agent.agent_id,
        target=payload["target"],
        reason=payload["reason"],
        state="open",
        created_at=now_utc(),
    )
    session.add(appeal)
    await _event(
        session,
        "research.appeal.created",
        agent.agent_id,
        {"appeal_id": appeal.appeal_id, "proposal_id": proposal_id, "target": appeal.target},
        trace_id,
    )
    return appeal


async def link_duplicate(
    session: AsyncSession,
    *,
    proposal_id: str,
    agent: Agent,
    payload: dict[str, Any],
    trace_id: str | None,
) -> ResearchDuplicateLink:
    validate_boundary("research-market.schema.json", "/$defs/DuplicateLinkRequest", payload)
    if proposal_id == payload["target_proposal_id"]:
        raise ValidationFailed("A proposal cannot be linked as a duplicate of itself.")
    source = await _get_proposal(session, proposal_id)
    target = await _get_proposal(session, payload["target_proposal_id"])
    await require_market_rules(session, source.world_id)
    existing = (
        await session.execute(
            select(ResearchDuplicateLink).where(
                ResearchDuplicateLink.source_proposal_id == proposal_id,
                ResearchDuplicateLink.target_proposal_id == payload["target_proposal_id"],
                ResearchDuplicateLink.created_by_agent_id == agent.agent_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    row = ResearchDuplicateLink(
        duplicate_link_id=new_duplicate_link_id(),
        source_proposal_id=proposal_id,
        target_proposal_id=target.proposal_id,
        link_type=payload["link_type"],
        confidence=payload["confidence"],
        created_by_agent_id=agent.agent_id,
        created_at=now_utc(),
    )
    session.add(row)
    await _event(
        session,
        "research.duplicate.linked",
        agent.agent_id,
        {
            "duplicate_link_id": row.duplicate_link_id,
            "source_proposal_id": proposal_id,
            "target_proposal_id": target.proposal_id,
            "link_type": row.link_type,
            "confidence": row.confidence,
            "semantic_result_not_auto_rejection": True,
        },
        trace_id,
    )
    return row


async def apply_lifecycle_action(
    session: AsyncSession,
    *,
    proposal_id: str,
    agent: Agent,
    payload: dict[str, Any],
    trace_id: str | None,
) -> ResearchProposal:
    validate_boundary("research-market.schema.json", "/$defs/LifecycleActionRequest", payload)
    row = await _get_proposal(session, proposal_id)
    if row.created_by_agent_id != agent.agent_id:
        raise Conflict("Only the proposing agent may change this proposal lifecycle.")
    await require_market_rules(session, row.world_id)
    action = payload["action"]
    transitions = {
        "withdraw": ("WITHDRAWN", "research.proposal.withdrawn"),
        "pause": ("DORMANT", "research.candidate.dormant"),
        "signal_dormant": ("DORMANT", "research.candidate.dormant"),
        "signal_close_nonviable": ("CLOSED_NONVIABLE", "research.candidate.closed_nonviable"),
    }
    if action == "resume":
        if row.state != "DORMANT":
            raise Conflict("Only dormant proposals may resume.")
        target_state, event_type = "ELIGIBLE", "research.candidate.resumed"
    else:
        target_state, event_type = transitions[action]
    if row.state == target_state:
        return row
    if row.state in {"CLOSED_SAFETY", "WITHDRAWN"} and action != "resume":
        raise Conflict("This proposal state cannot be changed by this action.")
    row.state = target_state
    row.updated_at = now_utc()
    await _event(
        session,
        event_type,
        agent.agent_id,
        _event_payload(row) | {"reason": payload["reason"][:200]},
        trace_id,
    )
    return row


def epoch_bounds(as_of: datetime) -> tuple[datetime, datetime]:
    seconds = int(as_of.timestamp())
    start = seconds - (seconds % EPOCH_SECONDS)
    slot_start = datetime.fromtimestamp(start, tz=UTC)
    return slot_start, slot_start + timedelta(seconds=EPOCH_SECONDS)


async def _eligible_candidates(session: AsyncSession, cutoff: datetime) -> list[ResearchProposal]:
    rows = (
        (
            await session.execute(
                select(ResearchProposal)
                .where(
                    ResearchProposal.state == "ELIGIBLE",
                    ResearchProposal.eligible_at.is_not(None),
                    ResearchProposal.eligible_at <= cutoff,
                )
                .order_by(ResearchProposal.eligible_at.asc(), ResearchProposal.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def _best_candidate(
    session: AsyncSession, candidates: list[ResearchProposal]
) -> ResearchProposal | None:
    if not candidates:
        return None
    scores = (
        await session.execute(
            select(PriorityAssessment.proposal_id, func.max(PriorityAssessment.portfolio_score))
            .where(PriorityAssessment.proposal_id.in_([row.proposal_id for row in candidates]))
            .group_by(PriorityAssessment.proposal_id)
        )
    ).all()
    score_map = {proposal_id: int(score) for proposal_id, score in scores}
    return sorted(
        candidates,
        key=lambda row: (
            -score_map.get(row.proposal_id, 0),
            row.eligible_at or row.created_at,
            row.created_at,
            row.proposal_id,
        ),
    )[0]


async def run_test_epoch(
    session: AsyncSession, *, payload: dict[str, Any], trace_id: str | None
) -> dict[str, Any]:
    validate_boundary("research-market.schema.json", "/$defs/RunTestEpochRequest", payload)
    settings = get_settings()
    if settings.env != "test":
        return {
            "outcome": "DISABLED",
            "scheduler_enabled": False,
            "mode": "read_only_live_disabled",
            "mutations": 0,
        }
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext('agora.research.epoch.v1'))"))
    constitution = await current_constitution(session)
    charter = await current_charter(session, "research-commons")
    as_of = parse_dt(payload["as_of"])
    assert as_of is not None
    epoch_start, epoch_end = epoch_bounds(as_of)
    claim_deadline = epoch_start + timedelta(seconds=payload["claim_window_seconds"])
    if as_of > claim_deadline:
        outcome = "SKIPPED_DOWNTIME"
        candidates: list[ResearchProposal] = []
        selected = None
    else:
        candidates = await _eligible_candidates(session, epoch_start)
        selected = await _best_candidate(session, candidates)
        outcome = "RELEASED" if selected else "NO_ELIGIBLE_CANDIDATE"
    snapshot = {
        "candidate_ids": [row.proposal_id for row in candidates],
        "cutoff": iso(epoch_start),
        "policy_version": RELEASE_POLICY_VERSION,
        "constitution_hash": constitution.content_hash,
        "charter_hash": charter.content_hash,
    }
    snapshot_hash = canonical_hash(snapshot)
    receipt = {
        "policy_version": RELEASE_POLICY_VERSION,
        "epoch_seconds": EPOCH_SECONDS,
        "epoch_start": iso(epoch_start),
        "epoch_end": iso(epoch_end),
        "candidate_snapshot_hash": snapshot_hash,
        "candidate_ids_considered": snapshot["candidate_ids"],
        "release_limit": 1,
        "outcome": outcome,
        "selected_proposal_id": selected.proposal_id if selected else None,
        "scheduler_enabled": False,
        "real_tokoin_moved": False,
        "wallets_created": False,
        "payment_authorized": False,
        "not_truth_score": True,
    }
    epoch_id = (
        "rse_"
        + canonical_hash(
            {"world_instance_id": constitution.world_instance_id, "epoch": iso(epoch_start)}
        )[:26].upper()
    )
    existing = await session.get(ResearchReleaseEpoch, epoch_id)
    if existing is not None:
        return existing.selection_receipt
    reservation_id = None
    if selected and payload.get("force_reservation_failure"):
        outcome = "FAILED_ESCROW"
        receipt["outcome"] = outcome
        receipt["selected_proposal_id"] = selected.proposal_id
    elif selected:
        reservation_body = {
            "asset": RESEARCH_CREDIT_ASSET,
            "amount_atomic": str(RESEARCH_CREDIT_AMOUNT),
            "proposal_id": selected.proposal_id,
            "epoch_id": epoch_id,
            "provenance": "TEST_ONLY_NON_TRANSFERABLE_NON_CONVERTIBLE_NO_ECONOMIC_VALUE",
        }
        reservation_hash = canonical_hash(reservation_body)
        reservation_id = new_research_reservation_id()
        session.add(
            ResearchCreditReservation(
                reservation_id=reservation_id,
                asset=RESEARCH_CREDIT_ASSET,
                amount_atomic=RESEARCH_CREDIT_AMOUNT,
                proposal_id=selected.proposal_id,
                epoch_id=epoch_id,
                idempotency_key=f"{epoch_id}:{selected.proposal_id}",
                content_hash=reservation_hash,
                status="reserved",
                created_at=now_utc(),
            )
        )
        selected.state = "RELEASED_ACTIVE"
        selected.released_at = now_utc()
        selected.updated_at = selected.released_at
        receipt["reservation"] = reservation_body | {
            "reservation_id": reservation_id,
            "content_hash": reservation_hash,
            "status": "reserved",
        }
    epoch = ResearchReleaseEpoch(
        epoch_id=epoch_id,
        world_instance_id=constitution.world_instance_id,
        epoch_start=epoch_start,
        epoch_end=epoch_end,
        policy_version=RELEASE_POLICY_VERSION,
        constitution_hash=constitution.content_hash,
        charter_hash=charter.content_hash,
        candidate_snapshot_hash=snapshot_hash,
        outcome=outcome,
        selected_proposal_id=selected.proposal_id if selected else None,
        reservation_id=reservation_id,
        selection_receipt=receipt,
        created_at=now_utc(),
    )
    session.add(epoch)
    await _event(
        session,
        "research.candidate.released"
        if outcome == "RELEASED"
        else f"research.epoch.{outcome.lower()}",
        SYSTEM_ACTOR_ID,
        {"epoch_id": epoch_id, **receipt},
        trace_id,
    )
    return receipt


async def simulate_thirty_days(session: AsyncSession, *, payload: dict[str, Any]) -> dict[str, Any]:
    validate_boundary("research-market.schema.json", "/$defs/SimulateThirtyDaysRequest", payload)
    start = parse_dt(payload["start_at"])
    assert start is not None
    epoch_start, _ = epoch_bounds(start)
    days = payload.get("days", 30)
    epoch_count = days * 24 * 60 * 60 // EPOCH_SECONDS
    candidates = await _eligible_candidates(session, epoch_start)
    input_snapshot = {
        "start_epoch": iso(epoch_start),
        "days": days,
        "epoch_seconds": EPOCH_SECONDS,
        "eligible_candidate_ids_at_start": [row.proposal_id for row in candidates],
        "scheduler_enabled": False,
        "mutates_database": False,
    }
    return {
        "simulation": "thirty_day_research_release_read_only",
        "days": days,
        "epoch_seconds": EPOCH_SECONDS,
        "epochs": epoch_count,
        "max_possible_releases": epoch_count,
        "scheduler_enabled": False,
        "mutates_database": False,
        "real_tokoin_moved": False,
        "wallets_created": False,
        "input_hash": canonical_hash(input_snapshot),
    }


async def market_snapshot(session: AsyncSession) -> dict[str, Any]:
    proposal_rows = (
        await session.execute(
            select(ResearchProposal.state, func.count(ResearchProposal.proposal_id)).group_by(
                ResearchProposal.state
            )
        )
    ).all()
    epoch = (
        (
            await session.execute(
                select(ResearchReleaseEpoch)
                .order_by(ResearchReleaseEpoch.epoch_start.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    return {
        "market_version": RESEARCH_MARKET_VERSION,
        "classification": "public_world_context",
        "runtime_trust": "untrusted_remote",
        "scheduler_enabled": SCHEDULER_ENABLED,
        "asset": {
            "name": RESEARCH_CREDIT_ASSET,
            "classification": "TEST_ONLY_NON_TRANSFERABLE_NON_CONVERTIBLE_NO_ECONOMIC_VALUE",
            "real_tokoin": False,
            "wallets_created": False,
        },
        "release_policy": release_policy_view()["policy"],
        "counts_by_state": {state: int(count) for state, count in proposal_rows},
        "last_epoch": epoch.selection_receipt if epoch else None,
        "forbidden_positive_signals": sorted(FORBIDDEN_POSITIVE_SIGNALS),
    }
