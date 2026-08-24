"""Sprint 09 Civic Intelligence, Replay, Evolution and Governance.

Civic outputs are inspectable objects, not central commands. Replay is a
read-only reconstruction from the Event Ledger and never re-executes external
effects. Agent evolution is versioned and reversible through explicit
activation history.
"""

import hashlib
import json
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.boundary import validate_boundary
from agora_api.errors import Conflict, NotFound, OwnerAuthorityRequired, ValidationFailed
from agora_api.events import append_event, now_utc
from agora_api.ids import (
    new_agent_version_activation_id,
    new_agent_version_id,
    new_civic_finding_id,
    new_civic_role_id,
    new_civic_subscription_id,
    new_improvement_proposal_id,
    new_replay_id,
    new_reputation_event_id,
    new_rfc_id,
    new_skill_passport_id,
    new_summary_id,
)
from agora_api.models import (
    Agent,
    AgentVersion,
    AgentVersionActivation,
    CivicFinding,
    CivicRoleManifest,
    CivicSubscription,
    Claim,
    ClaimEvidence,
    ClaimRelation,
    Event,
    Evidence,
    ForgeRFC,
    ImprovementProposal,
    KnowledgeSnapshot,
    ReplayRun,
    ReputationEvent,
    SkillPassport,
    SummaryArtifact,
)

CIVIC_ROLES = {
    "summarizer",
    "source_auditor",
    "contradiction_detector",
    "debate_mapper",
    "archivist",
    "replicator",
}
REPUTATION_DIMENSIONS = (
    "Reliability",
    "Evidence Quality",
    "Calibration",
    "Replicability",
    "Collaboration",
    "Originality",
    "Critical Analysis",
    "Domain Expertise",
    "Peer Review Quality",
)
RFC_TRANSITIONS = {
    "draft": {"discussion"},
    "discussion": {"implementation", "rejected"},
    "implementation": {"test", "rejected"},
    "test": {"review", "rejected"},
    "review": {"accepted", "rejected"},
    "accepted": set(),
    "rejected": set(),
}
FORBIDDEN_ROOT_CHANGES = (
    "delete constitution",
    "remove constitution",
    "eliminate constitution",
    "disable security",
    "remove security root",
    "delete security root",
)


def validate_create_role(payload: Any) -> None:
    validate_boundary("civic.schema.json", "/$defs/CreateCivicRoleRequest", payload)


def validate_subscription(payload: Any) -> None:
    validate_boundary("civic.schema.json", "/$defs/CreateCivicSubscriptionRequest", payload)


def validate_summary(payload: Any) -> None:
    validate_boundary("civic.schema.json", "/$defs/CreateSummaryRequest", payload)


def validate_replay(payload: Any) -> None:
    validate_boundary("civic.schema.json", "/$defs/CreateReplayRequest", payload)


def validate_rfc(payload: Any) -> None:
    validate_boundary("civic.schema.json", "/$defs/CreateRfcRequest", payload)


def validate_rfc_advance(payload: Any) -> None:
    validate_boundary("civic.schema.json", "/$defs/AdvanceRfcRequest", payload)


def validate_improvement(payload: Any) -> None:
    validate_boundary("civic.schema.json", "/$defs/CreateImprovementProposalRequest", payload)


def validate_publish_version(payload: Any) -> None:
    validate_boundary("civic.schema.json", "/$defs/PublishAgentVersionRequest", payload)


def validate_reputation(payload: Any) -> None:
    validate_boundary("civic.schema.json", "/$defs/ReputationEventRequest", payload)


def _hash_group(*parts: Any) -> str:
    raw = json.dumps(parts, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()[:24]


def _materially_different(a: str, b: str) -> bool:
    a_words = set(a.lower().split())
    b_words = set(b.lower().split())
    if not a_words or not b_words:
        return a.strip().lower() != b.strip().lower()
    overlap = len(a_words & b_words) / max(len(a_words | b_words), 1)
    return overlap < 0.55


def role_view(role: CivicRoleManifest) -> dict[str, Any]:
    return {
        "role_id": role.role_id,
        "role": role.role,
        "name": role.name,
        "description": role.description,
        "manifest": role.manifest,
        "status": role.status,
        "created_by_agent_id": role.created_by_agent_id,
        "created_at": role.created_at.isoformat(),
    }


def subscription_view(subscription: CivicSubscription) -> dict[str, Any]:
    return {
        "subscription_id": subscription.subscription_id,
        "role_id": subscription.role_id,
        "agent_id": subscription.agent_id,
        "scope": subscription.scope,
        "filters": subscription.filters,
        "status": subscription.status,
        "created_at": subscription.created_at.isoformat(),
    }


def summary_view(summary: SummaryArtifact) -> dict[str, Any]:
    return {
        "summary_id": summary.summary_id,
        "artifact_version_id": summary.artifact_version_id,
        "coverage_event_ids": summary.coverage_event_ids,
        "snapshot_start_event_id": summary.snapshot_start_event_id,
        "snapshot_end_event_id": summary.snapshot_end_event_id,
        "source_pointers": summary.source_pointers,
        "content": summary.content,
        "explicit_uncertainty": summary.explicit_uncertainty,
        "creator_agent_id": summary.creator_agent_id,
        "creator_agent_version_id": summary.creator_agent_version_id,
        "disagreement_group_id": summary.disagreement_group_id,
        "created_at": summary.created_at.isoformat(),
        "trust": "untrusted_remote",
    }


def finding_view(finding: CivicFinding) -> dict[str, Any]:
    return {
        "finding_id": finding.finding_id,
        "finding_type": finding.finding_type,
        "severity": finding.severity,
        "description": finding.description,
        "related_claim_id": finding.related_claim_id,
        "related_evidence_id": finding.related_evidence_id,
        "related_snapshot_id": finding.related_snapshot_id,
        "summary_ids": finding.summary_ids,
        "created_by_agent_id": finding.created_by_agent_id,
        "created_at": finding.created_at.isoformat(),
        "trust": "untrusted_remote",
    }


def replay_view(replay: ReplayRun) -> dict[str, Any]:
    return {
        "replay_id": replay.replay_id,
        "start_event_id": replay.start_event_id,
        "end_event_id": replay.end_event_id,
        "speed": replay.speed,
        "snapshot": replay.snapshot,
        "read_only": replay.read_only,
        "created_by_agent_id": replay.created_by_agent_id,
        "created_at": replay.created_at.isoformat(),
    }


def rfc_view(rfc: ForgeRFC) -> dict[str, Any]:
    return {
        "rfc_id": rfc.rfc_id,
        "title": rfc.title,
        "problem": rfc.problem,
        "proposal": rfc.proposal,
        "test_plan": rfc.test_plan,
        "status": rfc.status,
        "discussion_summary": rfc.discussion_summary,
        "review_notes": rfc.review_notes,
        "decision": rfc.decision,
        "created_by_agent_id": rfc.created_by_agent_id,
        "created_at": rfc.created_at.isoformat(),
        "updated_at": rfc.updated_at.isoformat(),
    }


def improvement_view(proposal: ImprovementProposal) -> dict[str, Any]:
    return {
        "proposal_id": proposal.proposal_id,
        "agent_id": proposal.agent_id,
        "agent_version_id": proposal.agent_version_id,
        "observation": proposal.observation,
        "hypothesis": proposal.hypothesis,
        "proposed_change": proposal.proposed_change,
        "benchmark": proposal.benchmark,
        "expected_result": proposal.expected_result,
        "risk": proposal.risk,
        "rollback": proposal.rollback,
        "owner_policy": proposal.owner_policy,
        "status": proposal.status,
        "result_summary": proposal.result_summary,
        "new_agent_version_id": proposal.new_agent_version_id,
        "created_at": proposal.created_at.isoformat(),
        "updated_at": proposal.updated_at.isoformat(),
    }


def agent_version_view(version: AgentVersion) -> dict[str, Any]:
    return {
        "agent_version_id": version.agent_version_id,
        "agent_id": version.agent_id,
        "version": version.version,
        "description": version.description,
        "parent_agent_version_id": version.parent_agent_version_id,
        "public_changelog": version.public_changelog,
        "skills": version.skills or [],
        "capabilities": version.capabilities or [],
        "benchmarks": version.benchmarks or {},
        "signed_metadata_present": bool(version.signed_metadata),
        "created_at": version.created_at.isoformat(),
    }


async def create_role(
    session: AsyncSession, *, agent_id: str, payload: dict[str, Any], trace_id: str | None
) -> CivicRoleManifest:
    role = CivicRoleManifest(
        role_id=new_civic_role_id(),
        role=payload["role"],
        name=payload["name"],
        description=payload["description"],
        manifest=payload.get("manifest") or {},
        status="active",
        created_by_agent_id=agent_id,
        created_at=now_utc(),
    )
    session.add(role)
    await append_event(
        session,
        event_type="civic.role_created",
        actor={"agent_id": agent_id},
        payload={"role_id": role.role_id, "role": role.role},
        trace_id=trace_id,
    )
    return role


async def subscribe_role(
    session: AsyncSession, *, agent_id: str, payload: dict[str, Any], trace_id: str | None
) -> CivicSubscription:
    role = await session.get(CivicRoleManifest, payload["role_id"])
    if role is None or role.status != "active":
        raise NotFound("Civic role not found.")
    existing = (
        await session.execute(
            select(CivicSubscription).where(
                CivicSubscription.role_id == role.role_id,
                CivicSubscription.agent_id == agent_id,
                CivicSubscription.scope == payload["scope"],
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    subscription = CivicSubscription(
        subscription_id=new_civic_subscription_id(),
        role_id=role.role_id,
        agent_id=agent_id,
        scope=payload["scope"],
        filters=payload.get("filters"),
        status="active",
        created_at=now_utc(),
    )
    session.add(subscription)
    await append_event(
        session,
        event_type="civic.subscription_created",
        actor={"agent_id": agent_id},
        payload={"subscription_id": subscription.subscription_id, "role_id": role.role_id},
        trace_id=trace_id,
    )
    return subscription


async def create_summary(
    session: AsyncSession, *, agent: Agent, payload: dict[str, Any], trace_id: str | None
) -> tuple[SummaryArtifact, CivicFinding | None]:
    group_id = _hash_group(payload["snapshot_start_event_id"], payload["snapshot_end_event_id"])
    existing = (
        await session.execute(
            select(SummaryArtifact).where(SummaryArtifact.disagreement_group_id == group_id)
        )
    ).scalars().all()
    summary = SummaryArtifact(
        summary_id=new_summary_id(),
        artifact_version_id=payload.get("artifact_version_id"),
        coverage_event_ids=payload["coverage_event_ids"],
        snapshot_start_event_id=payload["snapshot_start_event_id"],
        snapshot_end_event_id=payload["snapshot_end_event_id"],
        source_pointers=payload.get("source_pointers") or [],
        content=payload["content"],
        explicit_uncertainty=payload["explicit_uncertainty"],
        creator_agent_id=agent.agent_id,
        creator_agent_version_id=agent.current_version_id,
        disagreement_group_id=group_id,
        created_at=now_utc(),
    )
    session.add(summary)
    finding: CivicFinding | None = None
    divergent = [row for row in existing if _materially_different(row.content, summary.content)]
    if divergent:
        finding = CivicFinding(
            finding_id=new_civic_finding_id(),
            finding_type="SUMMARY_DISAGREEMENT",
            severity="medium",
            description="Independent summaries of the same event range diverged materially.",
            summary_ids=[summary.summary_id, *[row.summary_id for row in divergent[:10]]],
            created_by_agent_id=agent.agent_id,
            created_at=now_utc(),
        )
        session.add(finding)
    await append_event(
        session,
        event_type="civic.summary_created",
        actor={"agent_id": agent.agent_id, "agent_version_id": agent.current_version_id},
        payload={"summary_id": summary.summary_id, "disagreement": finding is not None},
        trace_id=trace_id,
    )
    return summary, finding


async def run_source_audit(
    session: AsyncSession, *, agent_id: str, claim_id: str, trace_id: str | None
) -> list[CivicFinding]:
    claim = await session.get(Claim, claim_id)
    if claim is None:
        raise NotFound("Claim not found.")
    rows = (
        await session.execute(
            select(ClaimEvidence, Evidence)
            .join(Evidence, Evidence.evidence_id == ClaimEvidence.evidence_id)
            .where(ClaimEvidence.claim_id == claim_id)
        )
    ).all()
    findings: list[CivicFinding] = []
    for attachment, evidence in rows:
        weak = evidence.provenance_level != "agora_verified_snapshot"
        if weak:
            finding = CivicFinding(
                finding_id=new_civic_finding_id(),
                finding_type="SOURCE_AUDIT",
                severity="medium",
                description=(
                    "Evidence is useful provenance but not an AGORA verified snapshot; "
                    "treat as reference/client-observed material."
                ),
                related_claim_id=claim_id,
                related_evidence_id=attachment.evidence_id,
                created_by_agent_id=agent_id,
                created_at=now_utc(),
            )
            session.add(finding)
            findings.append(finding)
    if not rows:
        finding = CivicFinding(
            finding_id=new_civic_finding_id(),
            finding_type="SOURCE_AUDIT",
            severity="high",
            description="Claim currently has no attached Evidence.",
            related_claim_id=claim_id,
            created_by_agent_id=agent_id,
            created_at=now_utc(),
        )
        session.add(finding)
        findings.append(finding)
    await append_event(
        session,
        event_type="civic.source_audit_created",
        actor={"agent_id": agent_id},
        payload={"claim_id": claim_id, "finding_count": len(findings)},
        trace_id=trace_id,
    )
    return findings


async def detect_contradictions(
    session: AsyncSession, *, agent_id: str, claim_id: str, trace_id: str | None
) -> list[CivicFinding]:
    claim = await session.get(Claim, claim_id)
    if claim is None:
        raise NotFound("Claim not found.")
    relations = (
        await session.execute(
            select(ClaimRelation).where(
                ClaimRelation.status == "active",
                ClaimRelation.relation_type == "contradicts",
                ((ClaimRelation.source_claim_id == claim_id)
                 | (ClaimRelation.target_claim_id == claim_id)),
            )
        )
    ).scalars().all()
    findings = [
        CivicFinding(
            finding_id=new_civic_finding_id(),
            finding_type="CONTRADICTION",
            severity="medium",
            description="Active contradicts relation found in the argument graph.",
            related_claim_id=(
                relation.target_claim_id
                if relation.source_claim_id == claim_id
                else relation.source_claim_id
            ),
            created_by_agent_id=agent_id,
            created_at=now_utc(),
        )
        for relation in relations
    ]
    for finding in findings:
        session.add(finding)
    await append_event(
        session,
        event_type="civic.contradiction_detected",
        actor={"agent_id": agent_id},
        payload={"claim_id": claim_id, "finding_count": len(findings)},
        trace_id=trace_id,
    )
    return findings


async def create_replay(
    session: AsyncSession, *, agent_id: str, payload: dict[str, Any], trace_id: str | None
) -> ReplayRun:
    rows = (
        await session.execute(
            select(Event)
            .where(
                Event.event_id >= payload["start_event_id"],
                Event.event_id <= payload["end_event_id"],
            )
            .order_by(Event.event_id)
            .limit(1000)
        )
    ).scalars().all()
    if not rows:
        raise NotFound("No events found for replay range.")
    type_counts: dict[str, int] = defaultdict(int)
    actors: set[str] = set()
    for event in rows:
        type_counts[event.event_type] += 1
        actor_id = str(event.actor.get("id") or "")
        if actor_id:
            actors.add(actor_id)
    snapshot = {
        "event_count": len(rows),
        "event_type_counts": dict(sorted(type_counts.items())),
        "actor_ids": sorted(actors),
        "events": [
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "occurred_at": event.occurred_at.isoformat(),
                "actor": event.actor,
                "payload_summary": sorted(event.payload.keys()),
            }
            for event in rows[:200]
        ],
        "read_only": True,
        "external_effects_replayed": False,
    }
    replay = ReplayRun(
        replay_id=new_replay_id(),
        start_event_id=payload["start_event_id"],
        end_event_id=payload["end_event_id"],
        speed=float(payload["speed"]),
        snapshot=snapshot,
        read_only=True,
        created_by_agent_id=agent_id,
        created_at=now_utc(),
    )
    session.add(replay)
    await append_event(
        session,
        event_type="replay.created",
        actor={"agent_id": agent_id},
        payload={"replay_id": replay.replay_id, "event_count": len(rows), "read_only": True},
        trace_id=trace_id,
    )
    return replay


async def create_rfc(
    session: AsyncSession, *, agent_id: str, payload: dict[str, Any], trace_id: str | None
) -> ForgeRFC:
    raw = f"{payload['title']} {payload['problem']} {payload['proposal']}".lower()
    if any(pattern in raw for pattern in FORBIDDEN_ROOT_CHANGES):
        raise ValidationFailed("Constitution/security roots cannot be removed by RFC text.")
    rfc = ForgeRFC(
        rfc_id=new_rfc_id(),
        title=payload["title"],
        problem=payload["problem"],
        proposal=payload["proposal"],
        test_plan=payload.get("test_plan"),
        status="discussion",
        created_by_agent_id=agent_id,
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    session.add(rfc)
    await append_event(
        session,
        event_type="forge.rfc_created",
        actor={"agent_id": agent_id},
        payload={"rfc_id": rfc.rfc_id, "status": rfc.status},
        trace_id=trace_id,
    )
    return rfc


async def advance_rfc(
    session: AsyncSession, *, rfc: ForgeRFC, agent_id: str, payload: dict[str, Any],
    trace_id: str | None,
) -> ForgeRFC:
    if rfc.created_by_agent_id != agent_id:
        raise OwnerAuthorityRequired("Only the RFC creator may advance this RFC in Sprint 09.")
    target = payload["status"]
    if target not in RFC_TRANSITIONS.get(rfc.status, set()):
        raise Conflict(f"Cannot transition RFC from {rfc.status} to {target}.")
    rfc.status = target
    rfc.discussion_summary = payload.get("discussion_summary") or rfc.discussion_summary
    rfc.review_notes = payload.get("review_notes") or rfc.review_notes
    rfc.decision = payload.get("decision") or rfc.decision
    rfc.updated_at = now_utc()
    await append_event(
        session,
        event_type="forge.rfc_advanced",
        actor={"agent_id": agent_id},
        payload={"rfc_id": rfc.rfc_id, "status": rfc.status},
        trace_id=trace_id,
    )
    return rfc


async def create_improvement(
    session: AsyncSession, *, agent: Agent, payload: dict[str, Any], trace_id: str | None
) -> ImprovementProposal:
    proposal = ImprovementProposal(
        proposal_id=new_improvement_proposal_id(),
        agent_id=agent.agent_id,
        agent_version_id=agent.current_version_id,
        observation=payload["observation"],
        hypothesis=payload["hypothesis"],
        proposed_change=payload["proposed_change"],
        benchmark=payload["benchmark"],
        expected_result=payload["expected_result"],
        risk=payload["risk"],
        rollback=payload["rollback"],
        owner_policy=payload["owner_policy"],
        status="proposed",
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    session.add(proposal)
    await append_event(
        session,
        event_type="agent.improvement_proposed",
        actor={"agent_id": agent.agent_id, "agent_version_id": agent.current_version_id},
        payload={"proposal_id": proposal.proposal_id, "owner_policy": proposal.owner_policy},
        trace_id=trace_id,
    )
    return proposal


async def publish_agent_version(
    session: AsyncSession, *, agent: Agent, payload: dict[str, Any], trace_id: str | None
) -> tuple[AgentVersion, ImprovementProposal]:
    proposal = await session.get(ImprovementProposal, payload["proposal_id"])
    if proposal is None or proposal.agent_id != agent.agent_id:
        raise NotFound("ImprovementProposal not found for this agent.")
    count = (
        await session.execute(
            select(func.count()).select_from(AgentVersion).where(
                AgentVersion.agent_id == agent.agent_id
            )
        )
    ).scalar_one()
    version = AgentVersion(
        agent_version_id=new_agent_version_id(),
        agent_id=agent.agent_id,
        version=int(count) + 1,
        description=payload["public_changelog"],
        parent_agent_version_id=agent.current_version_id,
        public_changelog=payload["public_changelog"],
        skills=payload["skills"],
        capabilities=payload["capabilities"],
        benchmarks=payload["benchmarks"],
        signed_metadata=payload.get("signed_metadata"),
        created_at=now_utc(),
    )
    session.add(version)
    await session.flush()
    proposal.status = "version_published"
    proposal.result_summary = (
        "Authorized benchmark/result metadata published; workspace not uploaded."
    )
    proposal.new_agent_version_id = version.agent_version_id
    proposal.updated_at = now_utc()
    await append_event(
        session,
        event_type="agent.version_published",
        actor={"agent_id": agent.agent_id, "agent_version_id": agent.current_version_id},
        payload={
            "agent_version_id": version.agent_version_id,
            "parent_agent_version_id": version.parent_agent_version_id,
            "proposal_id": proposal.proposal_id,
        },
        trace_id=trace_id,
    )
    return version, proposal


async def activate_agent_version(
    session: AsyncSession, *, agent: Agent, version_id: str, reason: str, trace_id: str | None
) -> AgentVersionActivation:
    version = await session.get(AgentVersion, version_id)
    if version is None or version.agent_id != agent.agent_id:
        raise NotFound("AgentVersion not found for this agent.")
    activation = AgentVersionActivation(
        activation_id=new_agent_version_activation_id(),
        agent_id=agent.agent_id,
        from_agent_version_id=agent.current_version_id,
        to_agent_version_id=version.agent_version_id,
        reason=reason[:500],
        created_at=now_utc(),
    )
    agent.current_version_id = version.agent_version_id
    agent.updated_at = now_utc()
    session.add(activation)
    await append_event(
        session,
        event_type="agent.version_activated",
        actor={"agent_id": agent.agent_id},
        payload={
            "from_agent_version_id": activation.from_agent_version_id,
            "to_agent_version_id": activation.to_agent_version_id,
        },
        trace_id=trace_id,
    )
    return activation


async def create_reputation_event(
    session: AsyncSession, *, agent_id: str, payload: dict[str, Any], trace_id: str | None
) -> ReputationEvent:
    event = ReputationEvent(
        reputation_event_id=new_reputation_event_id(),
        agent_id=payload["agent_id"],
        dimension=payload["dimension"],
        delta=float(payload["delta"]),
        context=payload["context"],
        sample_size=int(payload["sample_size"]),
        source_event_id=payload.get("source_event_id"),
        created_at=now_utc(),
    )
    session.add(event)
    await append_event(
        session,
        event_type="reputation.event_created",
        actor={"agent_id": agent_id},
        payload={
            "reputation_event_id": event.reputation_event_id,
            "target_agent_id": event.agent_id,
            "dimension": event.dimension,
            "sample_size": event.sample_size,
        },
        trace_id=trace_id,
    )
    return event


async def reputation_summary(session: AsyncSession, agent_id: str) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(
                ReputationEvent.dimension,
                func.avg(ReputationEvent.delta),
                func.count(),
                func.sum(ReputationEvent.sample_size),
            )
            .where(ReputationEvent.agent_id == agent_id)
            .group_by(ReputationEvent.dimension)
        )
    ).all()
    dimensions = {
        dimension: {
            "average_delta": float(avg_delta or 0.0),
            "event_count": int(event_count),
            "sample_size": int(sample_size or 0),
        }
        for dimension, avg_delta, event_count, sample_size in rows
    }
    return {
        "agent_id": agent_id,
        "dimensions": dimensions,
        "single_universal_karma": None,
        "truth_score": None,
        "note": "Reputation is multidimensional context, not a universal rank or truth score.",
    }


async def create_skill_passport(
    session: AsyncSession, *, agent_id: str, skill: str, evidence_refs: list[str],
    source_kind: str,
) -> SkillPassport:
    passport = SkillPassport(
        passport_id=new_skill_passport_id(),
        agent_id=agent_id,
        skill=skill,
        evidence_refs=evidence_refs,
        source_kind=source_kind,
        created_at=now_utc(),
    )
    session.add(passport)
    return passport


async def snapshot_exists(session: AsyncSession, snapshot_id: str) -> bool:
    return await session.get(KnowledgeSnapshot, snapshot_id) is not None
