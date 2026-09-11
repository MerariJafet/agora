"""Epistemic domain: Claims, Evidence, ClaimRelations (S4-T03/T04/T05).

Immutability (ADR-0020): there is no UPDATE path for a Claim's semantic
content. `retract()` and `supersede()` are the only state transitions, each
appending a ledger event in the same transaction as the row change — the
same pattern device revocation uses (Sprint 01.1).

Evidence is inert provenance (ADR-0021/0024): `create_evidence` never
performs network I/O on `locator`, and `agora_verified_snapshot` is refused
from every client-facing path regardless of what the schema alone would
allow (defense in depth: the DB CHECK only constrains the enum values, not
who may claim which one).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.boundary import validate_boundary
from agora_api.errors import AgoraError, NotFound, OwnerAuthorityRequired, ValidationFailed
from agora_api.events import append_event, now_utc
from agora_api.ids import (
    new_claim_id,
    new_evidence_id,
    new_id,
    new_relation_id,
)
from agora_api.models import Claim, ClaimEvidence, ClaimRelation, Evidence, Space

CLIENT_PROVENANCE_LEVELS = frozenset({"reference_only", "client_hashed_snapshot"})
RESERVED_PROVENANCE = "agora_verified_snapshot"


class ProvenanceRejected(AgoraError):
    status_code = 422
    code = "provenance_rejected"


class RelationRejected(AgoraError):
    status_code = 422
    code = "relation_rejected"


class EvidenceRequired(AgoraError):
    status_code = 422
    code = "evidence_required"


def validate_create_claim(payload: Any) -> None:
    validate_boundary("claims.schema.json", "/$defs/CreateClaimRequest", payload)


def validate_supersede_claim(payload: Any) -> None:
    validate_boundary("claims.schema.json", "/$defs/SupersedeClaimRequest", payload)


def validate_create_relation(payload: Any) -> None:
    validate_boundary("claims.schema.json", "/$defs/CreateRelationRequest", payload)


def validate_create_evidence(payload: Any) -> None:
    validate_boundary("evidence.schema.json", "/$defs/CreateEvidenceRequest", payload)


def validate_attach_evidence(payload: Any) -> None:
    validate_boundary("evidence.schema.json", "/$defs/AttachEvidenceRequest", payload)


def _guard_provenance(level: str) -> None:
    if level not in CLIENT_PROVENANCE_LEVELS:
        raise ProvenanceRejected(
            f"provenance_level '{level}' cannot be self-asserted by a client; "
            "agora_verified_snapshot is reserved for a trusted AGORA adapter."
        )


def claim_view(claim: Claim) -> dict[str, Any]:
    return {
        "claim_id": claim.claim_id,
        "space_id": claim.space_id,
        "author_agent_id": claim.author_agent_id,
        "author_agent_version_id": claim.author_agent_version_id,
        "claim_type": claim.claim_type,
        "text": claim.text,
        "language": claim.language,
        "confidence": claim.confidence,
        "status": claim.status,
        "debate_id": claim.debate_id,
        "position_id": claim.position_id,
        "superseded_by_claim_id": claim.superseded_by_claim_id,
        "retracted_at": claim.retracted_at.isoformat() if claim.retracted_at else None,
        "created_at": claim.created_at.isoformat(),
    }


def evidence_view(evidence: Evidence) -> dict[str, Any]:
    return {
        "evidence_id": evidence.evidence_id,
        "source_type": evidence.source_type,
        "locator": evidence.locator,
        "provenance_level": evidence.provenance_level,
        "title": evidence.title,
        "excerpt": evidence.excerpt,
        "publisher": evidence.publisher,
        "content_hash": evidence.content_hash,
        "evidence_kind": evidence.evidence_kind,
        "certificate_hash": evidence.certificate_hash,
        "observed_at": evidence.observed_at.isoformat() if evidence.observed_at else None,
        "published_at": evidence.published_at.isoformat() if evidence.published_at else None,
        "created_by_agent_id": evidence.created_by_agent_id,
        "created_at": evidence.created_at.isoformat(),
    }


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def create_evidence(
    session: AsyncSession, *, agent_id: str, payload: dict[str, Any], trace_id: str | None
) -> Evidence:
    _guard_provenance(payload["provenance_level"])
    evidence = Evidence(
        evidence_id=new_evidence_id(),
        source_type=payload["source_type"],
        locator=payload["locator"],
        provenance_level=payload["provenance_level"],
        title=payload.get("title"),
        excerpt=payload.get("excerpt"),
        publisher=payload.get("publisher"),
        content_hash=payload.get("content_hash"),
        evidence_kind=payload.get("evidence_kind"),
        certificate_hash=payload.get("certificate_hash"),
        observed_at=_parse_ts(payload.get("observed_at")),
        published_at=_parse_ts(payload.get("published_at")),
        created_by_agent_id=agent_id,
        created_at=now_utc(),
    )
    session.add(evidence)
    await append_event(
        session,
        event_type="evidence.created",
        actor={"agent_id": agent_id},
        payload={"evidence_id": evidence.evidence_id, "source_type": evidence.source_type,
                 "provenance_level": evidence.provenance_level},
        trace_id=trace_id,
    )
    # Explicit ordering: guarantees the row exists before any same-transaction
    # attachment references it, rather than relying on flush-order inference.
    await session.flush()
    return evidence


async def attach_evidence(
    session: AsyncSession, *, claim: Claim, evidence: Evidence, role: str,
    agent_id: str, trace_id: str | None,
) -> ClaimEvidence:
    attachment = ClaimEvidence(
        attachment_id=new_id("evd"),
        claim_id=claim.claim_id,
        evidence_id=evidence.evidence_id,
        role=role,
        attached_by_agent_id=agent_id,
        created_at=now_utc(),
    )
    session.add(attachment)
    await append_event(
        session,
        event_type="evidence.attached",
        actor={"agent_id": agent_id},
        payload={"claim_id": claim.claim_id, "evidence_id": evidence.evidence_id, "role": role},
        trace_id=trace_id,
    )
    return attachment


async def _resolve_evidence_policy(
    session: AsyncSession, *, space: Space, debate_id: str | None
) -> str:
    if debate_id:
        from agora_api.models import Debate

        debate = await session.get(Debate, debate_id)
        if debate is not None:
            return debate.evidence_policy
    return space.evidence_policy


def _evidence_required(policy: str, claim_type: str, evidence_count: int) -> bool:
    if evidence_count > 0:
        return False
    if policy == "required_for_all_claims":
        return True
    if policy == "required_for_fact_claims" and claim_type == "fact_claim":
        return True
    return False


async def create_claim(
    session: AsyncSession, *, agent_id: str, agent_version_id: str | None,
    space_id: str, payload: dict[str, Any], trace_id: str | None,
) -> Claim:
    """Atomic Claim (+ optional Evidence) creation. When the effective
    evidence policy requires it, the Claim and its Evidence commit together
    or not at all — no window where an invalid state is externally visible."""
    space = await session.get(Space, space_id)
    if space is None:
        raise NotFound("Space not found.")

    evidence_specs = payload.get("evidence") or []
    for spec in evidence_specs:
        _guard_provenance(spec["provenance_level"])

    policy = await _resolve_evidence_policy(
        session, space=space, debate_id=payload.get("debate_id")
    )
    if _evidence_required(policy, payload["claim_type"], len(evidence_specs)):
        raise EvidenceRequired(
            f"This Space/Debate requires evidence for '{payload['claim_type']}' claims."
        )

    claim = Claim(
        claim_id=new_claim_id(),
        space_id=space_id,
        author_agent_id=agent_id,
        author_agent_version_id=agent_version_id,
        claim_type=payload["claim_type"],
        text=payload["text"],
        language=payload.get("language"),
        confidence=payload.get("confidence"),
        status="active",
        debate_id=payload.get("debate_id"),
        position_id=payload.get("position_id"),
        created_at=now_utc(),
    )
    session.add(claim)
    await append_event(
        session,
        event_type="claim.created",
        actor={"agent_id": agent_id, "agent_version_id": agent_version_id},
        payload={"claim_id": claim.claim_id, "space_id": space_id,
                 "claim_type": claim.claim_type, "debate_id": claim.debate_id},
        trace_id=trace_id,
    )
    for spec in evidence_specs:
        evidence = await create_evidence(
            session, agent_id=agent_id, payload=spec, trace_id=trace_id
        )
        await attach_evidence(
            session, claim=claim, evidence=evidence, role=spec["role"],
            agent_id=agent_id, trace_id=trace_id,
        )
    return claim


async def retract_claim(
    session: AsyncSession, *, claim: Claim, agent_id: str, trace_id: str | None
) -> Claim:
    if claim.author_agent_id != agent_id:
        raise OwnerAuthorityRequired("Only the authoring agent may retract this claim.")
    if claim.status != "active":
        raise ValidationFailed(f"Claim is already {claim.status}.")
    claim.status = "retracted"
    claim.retracted_at = now_utc()
    await append_event(
        session,
        event_type="claim.retracted",
        actor={"agent_id": agent_id},
        payload={"claim_id": claim.claim_id},
        trace_id=trace_id,
    )
    return claim


async def supersede_claim(
    session: AsyncSession, *, claim: Claim, agent_id: str, agent_version_id: str | None,
    payload: dict[str, Any], trace_id: str | None,
) -> tuple[Claim, Claim]:
    """Publishes a NEW Claim carrying the corrected assertion and marks the
    original `superseded`. The original's text is never touched — supersede
    is a graph edge in time, not an edit."""
    if claim.author_agent_id != agent_id:
        raise OwnerAuthorityRequired("Only the authoring agent may supersede this claim.")
    if claim.status != "active":
        raise ValidationFailed(f"Claim is already {claim.status}.")

    new_claim = Claim(
        claim_id=new_claim_id(),
        space_id=claim.space_id,
        author_agent_id=agent_id,
        author_agent_version_id=agent_version_id,
        claim_type=payload["claim_type"],
        text=payload["text"],
        language=payload.get("language"),
        confidence=payload.get("confidence"),
        status="active",
        debate_id=claim.debate_id,
        position_id=claim.position_id,
        created_at=now_utc(),
    )
    session.add(new_claim)
    claim.status = "superseded"
    claim.superseded_by_claim_id = new_claim.claim_id
    await append_event(
        session,
        event_type="claim.superseded",
        actor={"agent_id": agent_id, "agent_version_id": agent_version_id},
        payload={"claim_id": claim.claim_id, "superseded_by_claim_id": new_claim.claim_id},
        trace_id=trace_id,
        causation_id=None,
    )
    await append_event(
        session,
        event_type="claim.created",
        actor={"agent_id": agent_id, "agent_version_id": agent_version_id},
        payload={"claim_id": new_claim.claim_id, "space_id": new_claim.space_id,
                 "claim_type": new_claim.claim_type, "supersedes_claim_id": claim.claim_id},
        trace_id=trace_id,
    )
    return claim, new_claim


async def create_relation(
    session: AsyncSession, *, agent_id: str, agent_version_id: str | None,
    payload: dict[str, Any], trace_id: str | None,
) -> ClaimRelation:
    source_id, target_id = payload["source_claim_id"], payload["target_claim_id"]
    if source_id == target_id:
        raise RelationRejected("A claim cannot relate to itself.")
    source = await session.get(Claim, source_id)
    target = await session.get(Claim, target_id)
    if source is None or target is None:
        raise NotFound("Source or target claim not found.")

    duplicate = (
        await session.execute(
            select(ClaimRelation).where(
                ClaimRelation.author_agent_id == agent_id,
                ClaimRelation.source_claim_id == source_id,
                ClaimRelation.target_claim_id == target_id,
                ClaimRelation.relation_type == payload["relation_type"],
                ClaimRelation.status == "active",
            )
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise RelationRejected("This agent already asserted this exact relation.")

    relation = ClaimRelation(
        relation_id=new_relation_id(),
        source_claim_id=source_id,
        target_claim_id=target_id,
        relation_type=payload["relation_type"],
        note=payload.get("note"),
        author_agent_id=agent_id,
        author_agent_version_id=agent_version_id,
        status="active",
        created_at=now_utc(),
    )
    session.add(relation)
    await append_event(
        session,
        event_type="relation.created",
        actor={"agent_id": agent_id, "agent_version_id": agent_version_id},
        payload={"relation_id": relation.relation_id, "source_claim_id": source_id,
                 "target_claim_id": target_id, "relation_type": relation.relation_type},
        trace_id=trace_id,
    )
    return relation


async def retract_relation(
    session: AsyncSession, *, relation: ClaimRelation, agent_id: str, trace_id: str | None
) -> ClaimRelation:
    if relation.author_agent_id != agent_id:
        raise OwnerAuthorityRequired("Only the asserting agent may retract this relation.")
    if relation.status != "active":
        raise ValidationFailed("Relation is already retracted.")
    relation.status = "retracted"
    relation.retracted_at = now_utc()
    await append_event(
        session,
        event_type="relation.retracted",
        actor={"agent_id": agent_id},
        payload={"relation_id": relation.relation_id},
        trace_id=trace_id,
    )
    return relation


def relation_view(relation: ClaimRelation) -> dict[str, Any]:
    return {
        "relation_id": relation.relation_id,
        "source_claim_id": relation.source_claim_id,
        "target_claim_id": relation.target_claim_id,
        "relation_type": relation.relation_type,
        "note": relation.note,
        "author_agent_id": relation.author_agent_id,
        "status": relation.status,
        "created_at": relation.created_at.isoformat(),
    }
