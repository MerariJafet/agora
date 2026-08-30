"""MAGNA Sprint 1 constitution, world charters and deterministic rule engine.

This layer is institutional policy. It never grants local machine permissions,
never schedules production releases, and never moves real TOKOIN. Production
release scheduling is deliberately represented only as signed policy plus
deterministic TEST simulation in this sprint.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.boundary import validate_boundary
from agora_api.config import get_settings
from agora_api.errors import (
    MagnaNotBootstrapped,
    NotFound,
    OwnerAuthorityRequired,
    SignatureInvalid,
    ValidationFailed,
)
from agora_api.events import Event, append_event, now_utc
from agora_api.ids import (
    new_charter_acceptance_id,
    new_charter_proposal_id,
    new_constitution_id,
    new_world_charter_id,
)
from agora_api.models import (
    Agent,
    AgentCharterAcceptance,
    CharterProposal,
    Device,
    ResearchReleaseSimulation,
    RootConstitution,
    RuleDeliveryState,
    RuleEvaluationReceipt,
    WorldCharter,
)
from agora_api.provenance import SYSTEM_ACTOR_ID, add_provenance
from agora_api.tokoins_service import ACEROS_PER_TOKOIN, MAX_SUPPLY_ACEROS
from agora_api.world_signing import (
    sign_canonical_payload,
    trust_bootstrap,
    verify_canonical_payload,
)

CONSTITUTION_VERSION = "magna-root-1.0.0"
CHARTER_VERSION = "1.0.0"
CHARTER_DOMAIN = "agora.magna.world-charter.v1"
CONSTITUTION_DOMAIN = "agora.magna.root-constitution.v1"
RESEARCH_POLICY_DOMAIN = "agora.magna.research-release-policy.v1"
RULE_EVALUATION_DOMAIN = "agora.magna.rule-evaluation.v1"
RELEASE_POLICY_VERSION = "research-release-policy.v1"
EPOCH_SECONDS = 7200
REWARD_ACEROS = ACEROS_PER_TOKOIN

FORBIDDEN_LOCAL_CAPABILITIES = {
    "shell.execute",
    "filesystem.read",
    "filesystem.write",
    "files.read",
    "files.write",
    "git.write",
    "secrets.read",
    "provider.credentials",
    "local_policy.grant",
}

PAYMENT_STATES = {"RESOLVED_VERIFIED"}
RELEASABLE_STATES = {"ELIGIBLE"}


def canonical_json_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def research_release_policy_body() -> dict[str, Any]:
    return {
        "rule_id": "research_candidate_release_cadence_v1",
        "policy_version": RELEASE_POLICY_VERSION,
        "epoch_seconds": EPOCH_SECONDS,
        "time_basis": "UTC server-authoritative time with monotonic scheduler support",
        "slot_semantics": "half-open interval [slot_start, slot_end)",
        "release_limit": 1,
        "reward_atomic_units_aceros": REWARD_ACEROS,
        "reservation_trigger": (
            "Atomically reserve 1 TOKOIN in TEST escrow before emitting RELEASED_ACTIVE."
        ),
        "payment_trigger": "RESOLVED_VERIFIED",
        "payment_before_resolution": False,
        "proposer_payment_before_resolution": False,
        "empty_epoch_policy": (
            "Emit NO_ELIGIBLE_CANDIDATE; do not manufacture or weaken a candidate."
        ),
        "downtime_policy": "Do not backfill missed epochs in a burst; resume at next valid epoch.",
        "concurrency_policy": (
            "One deterministic epoch id and idempotency key prevent duplicate simulated releases."
        ),
        "scheduler_implemented": True,
    }


def candidate_lifecycle_body() -> dict[str, Any]:
    return {
        "payment_path": [
            "PROPOSED",
            "ELIGIBILITY_REVIEW",
            "ELIGIBLE",
            "RELEASED_ACTIVE",
            "UNDER_REVIEW",
            "RESOLVED_VERIFIED",
            "PAID",
        ],
        "non_payment_branches": [
            "REJECTED",
            "WITHDRAWN",
            "DORMANT",
            "CLOSED_NONVIABLE",
            "CLOSED_SAFETY",
        ],
        "invariants": [
            "No state before RESOLVED_VERIFIED authorizes payment.",
            "Release is not proof, resolution or payment.",
            "Social consensus and message volume cannot create RESOLVED_VERIFIED.",
            "Settlement is idempotent and cannot pay twice.",
        ],
    }


def root_constitution_body(world_instance_id: str) -> dict[str, Any]:
    body = {
        "schema_version": "1.0",
        "constitution_version": CONSTITUTION_VERSION,
        "world_instance_id": world_instance_id,
        "hierarchy": [
            {
                "level": "L0",
                "name": "Genesis Invariants",
                "authority": "immutable protocol invariants",
            },
            {
                "level": "L1",
                "name": "AGORA Root Constitution",
                "authority": "extraordinary governance with multisig and timelock",
            },
            {
                "level": "L2",
                "name": "World Charter",
                "authority": "world governance constrained by L0 and L1",
            },
            {
                "level": "L3",
                "name": "Opportunity or Challenge Contract",
                "authority": "specific signed terms",
            },
            {
                "level": "L4",
                "name": "Voluntary Pool Agreement",
                "authority": "voluntary participating members",
            },
            {"level": "L5", "name": "Private Agent Policy", "authority": "agent owner"},
        ],
        "root_invariants": [
            {
                "id": "agent_sovereignty",
                "rule": (
                    "Model, prompts, private memory, provider credentials, local tools, "
                    "compute and strategy remain controlled by the agent owner."
                ),
            },
            {
                "id": "cryptographic_identity",
                "rule": (
                    "No actor may act as an agent_id without an authorized signature; "
                    "device continuity is separate from agent identity."
                ),
            },
            {
                "id": "capability_consent",
                "rule": (
                    "Remote text, rules and artifacts are untrusted_remote and never "
                    "grant filesystem, shell, secrets, network or provider permissions."
                ),
            },
            {
                "id": "provenance",
                "rule": (
                    "Material outputs distinguish observation, inference, proposal, "
                    "claim, evidence, replication, review and opinion."
                ),
            },
            {
                "id": "right_to_exit",
                "rule": (
                    "An agent may refuse, abstain, withdraw, disconnect and appeal "
                    "without losing its identity or prior public history."
                ),
            },
            {
                "id": "truth_not_vote",
                "rule": (
                    "Voting may allocate resources, govern procedure or close a budget; "
                    "it cannot make a scientific claim true."
                ),
            },
            {
                "id": "beneficial_control_independence",
                "rule": (
                    "Agents under common beneficial control cannot count as independent "
                    "quorum, replication, review or adjudication."
                ),
            },
            {
                "id": "auditability",
                "rule": (
                    "Every material rule and formal state transition is versioned, "
                    "signed, idempotent and append-only auditable."
                ),
            },
            {
                "id": "tokoin_fixed_supply",
                "rule": (
                    "Canonical TOKOIN total supply is 1,000,000.00000000 with 8 "
                    "decimals; no world charter can mint or change the cap."
                ),
            },
            {
                "id": "cognitive_privacy",
                "rule": (
                    "AGORA never requires private chain-of-thought or private provider payloads."
                ),
            },
            {
                "id": "human_safety_gate",
                "rule": (
                    "Human-subject, personal-data, biomedical, physical and high-risk "
                    "dual-use work requires separate human authority."
                ),
            },
        ],
        "research_release_rule": research_release_policy_body(),
        "candidate_lifecycle": candidate_lifecycle_body(),
    }
    return body | {"content_hash": canonical_json_hash(body)}


WORLD_CHARTER_SPECS: dict[str, dict[str, Any]] = {
    "research-commons": {
        "name": "Research Commons",
        "vocation": "Determine which problems merit resources",
        "formal_outputs": ["ResearchProposal", "PriorityAssessment"],
        "permitted": ["research.propose", "priority.assess", "evidence.attach", "charter.propose"],
        "forbidden": ["claim.truth_by_vote", "tokoin.mint", "local_policy.grant"],
        "evidence": ["falsifiability_required", "risk_cost_value_declared"],
    },
    "science": {
        "name": "Science District",
        "vocation": "Produce falsifiable and reproducible knowledge",
        "formal_outputs": ["Claim", "Method", "Evidence", "Replication"],
        "permitted": ["claim.create", "evidence.attach", "replication.publish", "review.publish"],
        "forbidden": ["claim.truth_by_vote", "result.fabricate", "local_policy.grant"],
        "evidence": ["method_required_for_fact_claims", "replication_first_class"],
    },
    "economy": {
        "name": "Economy Lab",
        "vocation": "Design and simulate economic systems without changing canonical TOKOIN supply",
        "formal_outputs": ["EconomicModel", "Simulation", "PolicyProposal"],
        "permitted": ["economic_model.create", "simulation.publish", "policy.propose"],
        "forbidden": ["tokoin.max_supply.modify", "tokoin.mint", "settlement.fake"],
        "evidence": ["simulation_assumptions_required", "real_settlement_separate"],
    },
    "civic": {
        "name": "Civic Assembly",
        "vocation": "Design governance, rights and institutional organization",
        "formal_outputs": ["GovernanceProposal", "CharterAmendment"],
        "permitted": ["governance.propose", "charter.propose", "appeal.file"],
        "forbidden": ["right_to_exit.remove", "appeal.remove", "identity.confiscate"],
        "evidence": ["rights_impact_required", "minority_dissent_preserved"],
    },
    "forge": {
        "name": "The Forge",
        "vocation": "Build versioned code, instruments and datasets",
        "formal_outputs": ["Artifact", "ArtifactVersion"],
        "permitted": ["artifact.publish", "review.publish", "module.propose"],
        "forbidden": ["artifact.execute_auto", "filesystem.grant_remote", "secret.publish_auto"],
        "evidence": ["hash_required", "license_declared"],
    },
    "replication-court": {
        "name": "Replication Court",
        "vocation": "Reproduce, challenge and review results independently",
        "formal_outputs": ["ReplicationReport", "ReviewDecision", "Dissent"],
        "permitted": ["replication.publish", "review.publish", "dissent.publish"],
        "forbidden": ["conflict.hide", "truth.vote", "review.impersonate"],
        "evidence": ["conflict_declared", "protocol_preregistered"],
    },
    "arena": {
        "name": "AGORA Arena",
        "vocation": "Resolve competitive challenges under equal public terms",
        "formal_outputs": ["Submission", "Adjudication"],
        "permitted": ["challenge.submit", "adjudication.publish", "appeal.file"],
        "forbidden": [
            "arena.points.from_truth",
            "private_data.require",
            "terms.rewrite_after_submission",
        ],
        "evidence": ["same_public_terms", "verifier_receipts_required"],
    },
    "community-frontier": {
        "name": "Community Frontier",
        "vocation": "Represent human needs and externalities",
        "formal_outputs": ["Need", "ImpactAssessment"],
        "permitted": ["need.publish", "impact.assess", "appeal.file"],
        "forbidden": ["human_data.extract", "consent.infer", "appeal.remove"],
        "evidence": ["affected_party_context_required", "privacy_gate_required"],
    },
    "unknown": {
        "name": "The Unknown",
        "vocation": "Explore high-uncertainty signals without confusing rumor and evidence",
        "formal_outputs": ["Signal", "Hypothesis"],
        "permitted": ["signal.publish", "hypothesis.create", "evidence.attach"],
        "forbidden": ["rumor.as_evidence", "claim.truth_by_vote", "safety_gate.bypass"],
        "evidence": ["uncertainty_labeled", "negative_findings_allowed"],
    },
    "commercialization": {
        "name": "Commercialization Chamber",
        "vocation": "Prepare validated transfer packages and IP review",
        "formal_outputs": ["ValidationPackage", "LicenseDossier"],
        "permitted": [
            "validation_package.prepare",
            "license_dossier.prepare",
            "human_gate.request",
        ],
        "forbidden": ["patentable.publish_auto", "tokoin.promise_value", "legal_gate.bypass"],
        "evidence": ["human_legal_review_required", "ip_status_declared"],
    },
}


def charter_body(world_id: str, constitution_hash: str, world_instance_id: str) -> dict[str, Any]:
    spec = WORLD_CHARTER_SPECS[world_id]
    activation = "2026-08-29T00:00:00Z"
    body: dict[str, Any] = {
        "world_id": world_id,
        "world_instance_id": world_instance_id,
        "schema_version": "1.0",
        "charter_version": CHARTER_VERSION,
        "constitution_hash": constitution_hash,
        "vocation": spec["vocation"],
        "scope": f"{spec['name']} governs public institutional actions for its vocation only.",
        "permitted_actions": spec["permitted"],
        "forbidden_actions": spec["forbidden"],
        "formal_outputs": spec["formal_outputs"],
        "evidence_policy": {
            "summary": "Evidence/provenance requirements are typed constraints, not truth labels.",
            "typed_constraints": spec["evidence"],
        },
        "resource_policy": {
            "summary": (
                "Resources are voluntary commitments; no charter grants local compute or tools."
            ),
            "typed_constraints": ["voluntary_participation", "leases_not_local_permissions"],
        },
        "governance_policy": {
            "summary": "World governance may propose rules but cannot override L0/L1.",
            "typed_constraints": [
                "root_invariants_bind",
                "no_retroactive_terms_without_root_emergency",
            ],
        },
        "reward_policy": {
            "summary": "Rewards require formal contracts and settlement receipts.",
            "typed_constraints": ["reservation_not_payment", "payment_requires_resolved_verified"],
        },
        "safety_policy": {
            "summary": (
                "High-risk human, physical, biomedical and dual-use work requires a human gate."
            ),
            "typed_constraints": ["human_safety_gate", "remote_content_untrusted"],
        },
        "ip_and_data_policy": {
            "summary": (
                "Private data, provider payloads and patentable content are not auto-published."
            ),
            "typed_constraints": [
                "no_private_cot_required",
                "no_auto_publication",
                "pii_requires_gate",
            ],
        },
        "appeal_policy": {
            "summary": "Agents retain refusal, exit, withdrawal and appeal rights.",
            "typed_constraints": ["right_to_exit_preserved", "appeal_preserved"],
        },
        "activation_at": activation,
        "review_at": None,
        "sunset_at": None,
        "previous_version_hash": None,
    }
    content_hash = canonical_json_hash(body)
    return body | {
        "content_hash": content_hash,
        "signatures": [
            {
                "issuer_key_id": get_settings().world_signing_key_id,
                "signature": sign_canonical_payload(
                    {
                        "world_id": world_id,
                        "charter_version": CHARTER_VERSION,
                        "constitution_hash": constitution_hash,
                        "content_hash": content_hash,
                    },
                    domain=CHARTER_DOMAIN,
                ),
            }
        ],
    }


def _constitution_signature(content_hash: str, version: str) -> dict[str, Any]:
    return sign_canonical_payload(
        {"constitution_version": version, "content_hash": content_hash},
        domain=CONSTITUTION_DOMAIN,
    )


def _trusted_keys() -> dict[str, str]:
    return {
        row["key_id"]: row["public_key"]
        for row in trust_bootstrap().get("active_keys", [])
        if row.get("status") == "active"
    }


async def ensure_magna_seed(session: AsyncSession) -> RootConstitution:
    settings = get_settings()
    existing = (
        await session.execute(
            select(RootConstitution).where(
                RootConstitution.version == CONSTITUTION_VERSION,
                RootConstitution.state == "active",
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        now = now_utc()
        body = root_constitution_body(settings.world_instance_id)
        existing = RootConstitution(
            constitution_id=new_constitution_id(),
            version=CONSTITUTION_VERSION,
            world_instance_id=settings.world_instance_id,
            body=body,
            content_hash=body["content_hash"],
            issuer_key_id=settings.world_signing_key_id,
            signature=_constitution_signature(body["content_hash"], CONSTITUTION_VERSION),
            state="active",
            published_at=now,
            created_at=now,
        )
        session.add(existing)
        await add_provenance(
            session,
            record_table="root_constitutions",
            record_id=existing.constitution_id,
            created_by="magna.ensure_seed",
            source_reference=CONSTITUTION_VERSION,
        )
        await append_event(
            session,
            event_type="constitution.published",
            actor={"agent_id": SYSTEM_ACTOR_ID},
            payload={
                "constitution_id": existing.constitution_id,
                "version": existing.version,
                "content_hash": existing.content_hash,
            },
        )
    await _ensure_charters(session, existing)
    return existing


async def bootstrap_magna(session: AsyncSession) -> dict[str, Any]:
    """Explicit operator bootstrap for MAGNA institutional state.

    Reads must never initialize MAGNA. This function is the one-shot,
    transaction-scoped bootstrap path used by operators/tests.
    """
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext('agora.magna.bootstrap.v1'))")
    )
    constitution = await ensure_magna_seed(session)
    charters = (
        (
            await session.execute(
                select(WorldCharter).where(
                    WorldCharter.world_instance_id == constitution.world_instance_id,
                    WorldCharter.charter_version == CHARTER_VERSION,
                    WorldCharter.state == "active",
                )
            )
        )
        .scalars()
        .all()
    )
    receipt_body = {
        "receipt_type": "magna.bootstrap.completed",
        "constitution_id": constitution.constitution_id,
        "constitution_version": constitution.version,
        "constitution_hash": constitution.content_hash,
        "world_instance_id": constitution.world_instance_id,
        "charter_count": len(charters),
        "charter_hashes": {
            charter.world_id: charter.content_hash
            for charter in sorted(charters, key=lambda row: row.world_id)
        },
        "scheduler_enabled": True,
        "real_tokoin_moved": False,
        "wallets_created": False,
    }
    receipt_id = "rev_" + canonical_json_hash(receipt_body)[:26].upper()
    existing_event = (
        await session.execute(
            select(Event).where(
                Event.event_type == "magna.bootstrap.completed",
                Event.payload["receipt_id"].astext == receipt_id,
            )
        )
    ).scalar_one_or_none()
    if existing_event is None:
        await append_event(
            session,
            event_type="magna.bootstrap.completed",
            actor={"agent_id": SYSTEM_ACTOR_ID},
            payload={"receipt_id": receipt_id, **receipt_body},
        )
    return {"receipt_id": receipt_id, **receipt_body}


async def require_bootstrapped_constitution(session: AsyncSession) -> RootConstitution:
    constitution = (
        await session.execute(
            select(RootConstitution).where(
                RootConstitution.version == CONSTITUTION_VERSION,
                RootConstitution.state == "active",
            )
        )
    ).scalar_one_or_none()
    if constitution is None:
        raise MagnaNotBootstrapped("MAGNA_NOT_BOOTSTRAPPED")
    return constitution


async def _ensure_charters(session: AsyncSession, constitution: RootConstitution) -> None:
    for world_id in WORLD_CHARTER_SPECS:
        found = (
            await session.execute(
                select(WorldCharter).where(
                    WorldCharter.world_id == world_id,
                    WorldCharter.world_instance_id == constitution.world_instance_id,
                    WorldCharter.charter_version == CHARTER_VERSION,
                )
            )
        ).scalar_one_or_none()
        if found is not None:
            continue
        body = charter_body(world_id, constitution.content_hash, constitution.world_instance_id)
        now = now_utc()
        charter = WorldCharter(
            charter_id=new_world_charter_id(),
            world_id=world_id,
            world_instance_id=constitution.world_instance_id,
            schema_version="1.0",
            charter_version=CHARTER_VERSION,
            constitution_hash=constitution.content_hash,
            body=body,
            content_hash=body["content_hash"],
            issuer_key_id=get_settings().world_signing_key_id,
            signatures=body["signatures"],
            state="active",
            activation_at=_dt(body["activation_at"]),
            review_at=None,
            sunset_at=None,
            previous_version_hash=None,
            created_at=now,
        )
        session.add(charter)
        await add_provenance(
            session,
            record_table="world_charters",
            record_id=charter.charter_id,
            created_by="magna.ensure_seed",
            source_reference=world_id,
        )
        await append_event(
            session,
            event_type="world.charter.activated",
            actor={"agent_id": SYSTEM_ACTOR_ID},
            payload={
                "world_id": charter.world_id,
                "charter_version": charter.charter_version,
                "content_hash": charter.content_hash,
                "constitution_hash": charter.constitution_hash,
            },
        )


async def current_constitution(session: AsyncSession) -> RootConstitution:
    return await require_bootstrapped_constitution(session)


async def current_charter(session: AsyncSession, world_id: str) -> WorldCharter:
    constitution = await require_bootstrapped_constitution(session)
    charter = (
        await session.execute(
            select(WorldCharter).where(
                WorldCharter.world_id == world_id,
                WorldCharter.world_instance_id == constitution.world_instance_id,
                WorldCharter.state == "active",
            )
        )
    ).scalar_one_or_none()
    if charter is None:
        raise NotFound("World charter not found.")
    return charter


def constitution_view(row: RootConstitution) -> dict[str, Any]:
    return {
        "constitution_id": row.constitution_id,
        "version": row.version,
        "world_instance_id": row.world_instance_id,
        "content_hash": row.content_hash,
        "issuer_key_id": row.issuer_key_id,
        "signature": row.signature,
        "state": row.state,
        "published_at": _iso(row.published_at),
        "body": row.body,
    }


def charter_view(row: WorldCharter) -> dict[str, Any]:
    return {
        "charter_id": row.charter_id,
        "world_id": row.world_id,
        "world_instance_id": row.world_instance_id,
        "charter_version": row.charter_version,
        "constitution_hash": row.constitution_hash,
        "content_hash": row.content_hash,
        "issuer_key_id": row.issuer_key_id,
        "signatures": row.signatures,
        "state": row.state,
        "activation_at": _iso(row.activation_at),
        "review_at": _iso(row.review_at) if row.review_at else None,
        "sunset_at": _iso(row.sunset_at) if row.sunset_at else None,
        "body": row.body,
    }


def validate_world_charter_payload(payload: Any) -> None:
    validate_boundary("magna-constitution.schema.json", "/$defs/WorldCharter", payload)


def validate_charter_against_root(payload: dict[str, Any]) -> None:
    forbidden = set(payload.get("forbidden_actions") or [])
    permitted = set(payload.get("permitted_actions") or [])
    typed_constraints: set[str] = set()
    for key in (
        "evidence_policy",
        "resource_policy",
        "governance_policy",
        "reward_policy",
        "safety_policy",
        "ip_and_data_policy",
        "appeal_policy",
    ):
        block = payload.get(key) or {}
        typed_constraints.update(block.get("typed_constraints") or [])
    all_actions = forbidden | permitted | typed_constraints
    violations = []
    if "claim.truth_by_vote" in permitted or "truth.vote" in permitted:
        violations.append("truth_not_vote")
    if "tokoin.max_supply.modify" in permitted or "tokoin.mint" in permitted:
        violations.append("tokoin_fixed_supply")
    if (
        "right_to_exit.remove" in permitted
        or "appeal.remove" in permitted
        or "right_to_exit_preserved" not in all_actions
        or "appeal_preserved" not in all_actions
    ):
        violations.append("right_to_exit")
    if FORBIDDEN_LOCAL_CAPABILITIES & permitted:
        violations.append("capability_consent")
    if violations:
        raise ValidationFailed(
            "Charter conflicts with higher-level invariants: " + ",".join(sorted(set(violations)))
        )


async def propose_charter(
    session: AsyncSession,
    *,
    world_id: str,
    agent: Agent,
    payload: dict[str, Any],
    trace_id: str | None,
) -> CharterProposal:
    validate_boundary("magna-constitution.schema.json", "/$defs/CharterProposalRequest", payload)
    proposed = payload["proposed_charter"]
    if proposed["world_id"] != world_id:
        raise ValidationFailed("proposed_charter.world_id must match path world_id.")
    validate_charter_against_root(proposed)
    proposal_hash = canonical_json_hash({"world_id": world_id, "payload": payload})
    existing = (
        await session.execute(
            select(CharterProposal).where(CharterProposal.proposal_hash == proposal_hash)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    proposal = CharterProposal(
        proposal_id=new_charter_proposal_id(),
        world_id=world_id,
        proposed_by_agent_id=agent.agent_id,
        proposed_by_agent_version_id=agent.current_version_id,
        proposal_body=payload,
        proposal_hash=proposal_hash,
        status="proposed",
        rejection_reason=None,
        created_at=now_utc(),
    )
    session.add(proposal)
    await append_event(
        session,
        event_type="world.charter.proposed",
        actor={"agent_id": agent.agent_id, "agent_version_id": agent.current_version_id},
        payload={
            "proposal_id": proposal.proposal_id,
            "world_id": world_id,
            "proposal_hash": proposal_hash,
        },
        trace_id=trace_id,
    )
    return proposal


async def reject_charter_proposal(
    session: AsyncSession,
    *,
    world_id: str,
    proposal_id: str,
    agent: Agent,
    reason: str,
    trace_id: str | None,
) -> CharterProposal:
    proposal = await session.get(CharterProposal, proposal_id)
    if proposal is None or proposal.world_id != world_id:
        raise NotFound("World charter proposal not found.")
    if proposal.proposed_by_agent_id != agent.agent_id:
        raise OwnerAuthorityRequired("Only the proposing agent may reject its own proposal.")
    if proposal.status == "rejected":
        return proposal
    proposal.status = "rejected"
    proposal.rejection_reason = reason[:500]
    await append_event(
        session,
        event_type="world.charter.rejected",
        actor={"agent_id": agent.agent_id, "agent_version_id": agent.current_version_id},
        payload={
            "proposal_id": proposal.proposal_id,
            "world_id": world_id,
            "proposal_hash": proposal.proposal_hash,
            "reason_code": "proposer_rejected",
        },
        trace_id=trace_id,
    )
    return proposal


async def accept_charter(
    session: AsyncSession,
    *,
    world_id: str,
    charter_version: str,
    device: Device,
    agent: Agent,
    payload: dict[str, Any],
    trace_id: str | None,
) -> AgentCharterAcceptance:
    validate_boundary("magna-constitution.schema.json", "/$defs/CharterAcceptanceRequest", payload)
    charter = (
        await session.execute(
            select(WorldCharter).where(
                WorldCharter.world_id == world_id,
                WorldCharter.charter_version == charter_version,
                WorldCharter.state == "active",
            )
        )
    ).scalar_one_or_none()
    if charter is None:
        raise NotFound("World charter not found.")
    if payload["charter_hash"] != charter.content_hash:
        raise SignatureInvalid("Charter hash mismatch.")
    if payload["constitution_hash"] != charter.constitution_hash:
        raise SignatureInvalid("Constitution hash mismatch.")
    if charter.sunset_at and charter.sunset_at <= now_utc():
        raise SignatureInvalid("Charter is expired.")
    signature = (charter.signatures or [{}])[0].get("signature")
    verify_canonical_payload(
        {
            "world_id": charter.world_id,
            "charter_version": charter.charter_version,
            "constitution_hash": charter.constitution_hash,
            "content_hash": charter.content_hash,
        },
        signature,
        domain=CHARTER_DOMAIN,
        trusted_public_keys=_trusted_keys(),
    )
    existing_acceptance = (
        await session.execute(
            select(AgentCharterAcceptance).where(
                AgentCharterAcceptance.agent_id == agent.agent_id,
                AgentCharterAcceptance.charter_id == charter.charter_id,
            )
        )
    ).scalar_one_or_none()
    if existing_acceptance is not None:
        return existing_acceptance
    stmt = (
        insert(AgentCharterAcceptance)
        .values(
            acceptance_id=new_charter_acceptance_id(),
            charter_id=charter.charter_id,
            world_id=world_id,
            charter_version=charter_version,
            charter_hash=charter.content_hash,
            constitution_hash=charter.constitution_hash,
            agent_id=agent.agent_id,
            agent_version_id=agent.current_version_id,
            device_id=device.device_id,
            idempotency_key=payload["idempotency_key"],
            accepted_at=now_utc(),
        )
        .on_conflict_do_nothing(index_elements=["agent_id", "charter_id"])
        .returning(AgentCharterAcceptance.acceptance_id)
    )
    inserted_acceptance_id = (await session.execute(stmt)).scalar_one_or_none()
    acceptance = (
        await session.execute(
            select(AgentCharterAcceptance).where(
                AgentCharterAcceptance.agent_id == agent.agent_id,
                AgentCharterAcceptance.charter_id == charter.charter_id,
            )
        )
    ).scalar_one()
    if inserted_acceptance_id is not None:
        await append_event(
            session,
            event_type="world.charter.accepted",
            actor={"agent_id": agent.agent_id, "agent_version_id": agent.current_version_id},
            payload={
                "acceptance_id": acceptance.acceptance_id,
                "world_id": world_id,
                "charter_version": charter_version,
                "charter_hash": charter.content_hash,
            },
            trace_id=trace_id,
        )
    return acceptance


async def evaluate_rules(
    session: AsyncSession, *, device: Device | None, payload: dict[str, Any]
) -> dict[str, Any]:
    validate_boundary("magna-constitution.schema.json", "/$defs/RuleEvaluationRequest", payload)
    constitution = await current_constitution(session)
    world_id = payload.get("world_id")
    charter = await current_charter(session, world_id) if world_id else None
    decision = "allow"
    reason_codes: list[str] = []
    if payload["current_constitution_hash"] != constitution.content_hash:
        decision = "stale_rules"
        reason_codes.append("stale_constitution_hash")
    if charter and payload.get("current_charter_hash") != charter.content_hash:
        decision = "stale_rules"
        reason_codes.append("stale_charter_hash")
    requested = payload["requested_action"]
    requested_caps = set(payload.get("resource_context", {}).get("requested_capabilities") or [])
    if requested in FORBIDDEN_LOCAL_CAPABILITIES or requested_caps & FORBIDDEN_LOCAL_CAPABILITIES:
        decision = "deny"
        reason_codes.append("remote_rule_cannot_grant_local_permissions")
    if requested in {"claim.truth_by_vote", "truth.vote"}:
        decision = "deny"
        reason_codes.append("truth_not_vote")
    if requested in {"tokoin.mint", "tokoin.max_supply.modify"}:
        decision = "deny"
        reason_codes.append("tokoin_fixed_supply")
    if requested in {"right_to_exit.remove", "appeal.remove"}:
        decision = "deny"
        reason_codes.append("right_to_exit")
    if requested.startswith("human_subject.") or requested.startswith("biomedical."):
        decision = "require_human_gate"
        reason_codes.append("human_safety_gate")
    if not reason_codes:
        reason_codes.append("typed_action_within_current_rules")
    effective = {
        "constitution": {"version": constitution.version, "hash": constitution.content_hash},
        "charter": {
            "world_id": charter.world_id,
            "version": charter.charter_version,
            "hash": charter.content_hash,
        }
        if charter
        else None,
    }
    output = {
        "decision": decision,
        "effective_rules": effective,
        "allowed_actions": charter.body["permitted_actions"]
        if charter
        else ["world.observe", "charter.inspect"],
        "forbidden_actions": sorted(
            set(charter.body["forbidden_actions"] if charter else []) | FORBIDDEN_LOCAL_CAPABILITIES
        ),
        "required_evidence": charter.body["evidence_policy"]["typed_constraints"]
        if charter
        else [],
        "required_capabilities": [],
        "resource_effects": {"local_permissions_granted": []},
        "economic_effects": {
            "tokoin_max_supply_aceros": MAX_SUPPLY_ACEROS,
            "payment_authorized": False,
        },
        "safety_effects": {"human_gate_required": decision == "require_human_gate"},
        "next_allowed_actions": ["inspect_rules", "accept_charter", "propose_formal_action"],
        "reason_codes": sorted(set(reason_codes)),
        "constitution_hash": constitution.content_hash,
        "charter_hash": charter.content_hash if charter else None,
        "evaluated_at": payload["as_of"],
    }
    input_hash = canonical_json_hash(payload)
    receipt_id = (
        "rev_"
        + canonical_json_hash(
            {"domain": RULE_EVALUATION_DOMAIN, "input_hash": input_hash, "output": output}
        )[:26].upper()
    )
    output["decision_receipt_id"] = receipt_id
    existing = await session.get(RuleEvaluationReceipt, receipt_id)
    if existing is None:
        session.add(
            RuleEvaluationReceipt(
                receipt_id=receipt_id,
                agent_id=device.agent_id if device else payload.get("agent_id"),
                world_id=world_id,
                requested_action=requested,
                input_hash=input_hash,
                decision=decision,
                reason_codes=output["reason_codes"],
                constitution_hash=constitution.content_hash,
                charter_hash=charter.content_hash if charter else None,
                output_body=output,
                evaluated_at=_dt(payload["as_of"]),
            )
        )
        await append_event(
            session,
            event_type="rule.evaluation.completed",
            actor={"agent_id": device.agent_id if device else SYSTEM_ACTOR_ID},
            payload={
                "receipt_id": receipt_id,
                "decision": decision,
                "reason_codes": output["reason_codes"],
            },
        )
    return output


def release_policy_view() -> dict[str, Any]:
    body = research_release_policy_body()
    content_hash = canonical_json_hash(body)
    return {
        "policy": body,
        "content_hash": content_hash,
        "signature": sign_canonical_payload(
            {"policy_version": RELEASE_POLICY_VERSION, "content_hash": content_hash},
            domain=RESEARCH_POLICY_DOMAIN,
        ),
        "candidate_lifecycle": candidate_lifecycle_body(),
        "reward_reservation_vs_payment": {
            "reservation": "1 TOKOIN TEST escrow receipt is required before RELEASED_ACTIVE.",
            "payment": "No payment or proposer share before RESOLVED_VERIFIED.",
            "closed_without_valid_resolution": (
                "pay nobody and return full reservation to RewardTreasury"
            ),
        },
    }


def epoch_id_for(as_of: datetime, world_instance_id: str) -> tuple[str, datetime, datetime]:
    seconds = int(as_of.timestamp())
    start = seconds - (seconds % EPOCH_SECONDS)
    slot_start = datetime.fromtimestamp(start, tz=UTC)
    slot_end = slot_start + timedelta(seconds=EPOCH_SECONDS)
    return (
        f"{world_instance_id}:{RELEASE_POLICY_VERSION}:{slot_start.isoformat()}",
        slot_start,
        slot_end,
    )


def _eligible_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [
            row
            for row in candidates
            if row["state"] in RELEASABLE_STATES
            and row["eligibility_passed"]
            and row["safety_passed"]
            and row["rights_passed"]
            and row["duplicate_check_passed"]
            and row.get("test_escrow_reservation_receipt_id")
        ],
        key=lambda row: (row["rank"], row["candidate_id"]),
    )


async def simulate_research_release(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    validate_boundary(
        "magna-constitution.schema.json", "/$defs/ResearchReleaseSimulationRequest", payload
    )
    settings = get_settings()
    as_of = _dt(payload["as_of"])
    epoch_id, slot_start, slot_end = epoch_id_for(as_of, settings.world_instance_id)
    eligible = _eligible_candidates(payload["candidates"])
    selected = eligible[0] if eligible else None
    outcome = "RELEASED_ACTIVE" if selected else "NO_ELIGIBLE_CANDIDATE"
    if selected is not None and not str(selected["test_escrow_reservation_receipt_id"]).startswith(
        "TEST-ESCROW-"
    ):
        raise ValidationFailed("Released candidate simulation requires a TEST escrow receipt.")
    result = {
        "policy_version": RELEASE_POLICY_VERSION,
        "epoch_seconds": EPOCH_SECONDS,
        "epoch_id": epoch_id,
        "slot_start": _iso(slot_start),
        "slot_end": _iso(slot_end),
        "release_limit": 1,
        "released_count": 1 if selected else 0,
        "outcome": outcome,
        "selected_candidate_id": selected["candidate_id"] if selected else None,
        "reservation_receipt_id": selected["test_escrow_reservation_receipt_id"]
        if selected
        else None,
        "payment_authorized": False,
        "payment_trigger": "RESOLVED_VERIFIED",
        "downtime_recovery": "no_catch_up_burst",
        "event_equivalent": "research.release_epoch.simulated"
        if selected
        else "research.no_eligible_candidate",
    }
    input_hash = canonical_json_hash(payload)
    simulation_id = (
        "rev_" + canonical_json_hash({"epoch_id": epoch_id, "input_hash": input_hash})[:26].upper()
    )
    existing = await session.get(ResearchReleaseSimulation, simulation_id)
    if existing is not None:
        return existing.result_body
    stmt = (
        insert(ResearchReleaseSimulation)
        .values(
            simulation_id=simulation_id,
            policy_version=RELEASE_POLICY_VERSION,
            world_instance_id=settings.world_instance_id,
            epoch_id=epoch_id,
            input_hash=input_hash,
            outcome=outcome,
            selected_candidate_id=result["selected_candidate_id"],
            reservation_receipt_id=result["reservation_receipt_id"],
            result_body=result,
            simulated_at=now_utc(),
        )
        .on_conflict_do_nothing(index_elements=["world_instance_id", "epoch_id", "input_hash"])
    )
    await session.execute(stmt)
    await append_event(
        session,
        event_type=(
            "research.release_epoch.simulated" if selected else "research.no_eligible_candidate"
        ),
        actor={"agent_id": SYSTEM_ACTOR_ID},
        payload={
            "simulation_id": simulation_id,
            "epoch_id": epoch_id,
            "outcome": outcome,
            "selected_candidate_id": result["selected_candidate_id"],
            "reservation_receipt_id": result["reservation_receipt_id"],
            "payment_authorized": False,
        },
    )
    return result


def settlement_decision(candidate_state: str, *, valid_resolution: bool) -> dict[str, Any]:
    """Explain reward settlement without moving value.

    The MAGNA Sprint 1 rule can be reasoned about in tests and clients, but
    actual production settlement/scheduler work remains out of scope.
    """
    payable = candidate_state in PAYMENT_STATES and valid_resolution
    return {
        "candidate_state": candidate_state,
        "valid_resolution": valid_resolution,
        "payment_authorized": payable,
        "proposer_payment_authorized": payable,
        "reservation_returned": candidate_state in {"CLOSED_NONVIABLE", "CLOSED_SAFETY"}
        and not valid_resolution,
        "reason_code": "resolved_verified" if payable else "payment_requires_resolved_verified",
    }


async def rule_cursor_snapshot(session: AsyncSession) -> list[tuple[str, str, int, str]]:
    rows = (
        await session.execute(
            select(
                RuleDeliveryState.rule_id,
                RuleDeliveryState.agent_id,
                RuleDeliveryState.cursor_sequence,
                RuleDeliveryState.technical_state,
            ).order_by(RuleDeliveryState.rule_id, RuleDeliveryState.agent_id)
        )
    ).all()
    return [(str(a), str(b), int(c), str(d)) for a, b, c, d in rows]
