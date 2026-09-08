"""MAGNA Knowledge Ledger service.

The ledger stores formal, content-addressed research objects and provenance
edges. Remote URLs/files/code are inert metadata; this module never fetches,
executes or renders them.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.boundary import validate_boundary
from agora_api.config import get_settings
from agora_api.errors import AgoraError, Conflict, NotFound, ValidationFailed
from agora_api.events import append_event, now_utc
from agora_api.ids import (
    new_knowledge_edge_id,
    new_knowledge_object_id,
    new_merkle_batch_id,
    new_resolution_receipt_id,
)
from agora_api.magna_constitution import current_charter, current_constitution
from agora_api.models import (
    Agent,
    MagnaKnowledgeEdge,
    MagnaKnowledgeObject,
    MagnaMerkleBatch,
    MagnaResolutionReceipt,
)

SCHEMA = "magna-knowledge-ledger.schema.json"
OPEN_LICENSE_RIGHTS = "explicit_open_license"
SECRETS_RE = (
    "api_key",
    "authorization",
    "bearer ",
    "private_key",
    "-----begin",
    "chain_of_thought",
    "cot",
)
GRAPH_RELATIONS = {
    "was_derived_from",
    "used",
    "uses",
    "was_generated_by",
    "supersedes",
    "depends_on",
    "parent_of",
    "requests_revision_of",
}


class KnowledgeLedgerViolation(AgoraError):
    status_code = 422
    code = "knowledge_ledger_violation"


def canonical_json_hash(payload: Any, *, domain: str) -> str:
    raw = json.dumps(
        {"domain": domain, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def validate_create_object(payload: Any) -> None:
    validate_boundary(SCHEMA, "/$defs/CreateKnowledgeObjectRequest", payload)


def validate_register_protocol(payload: Any) -> None:
    validate_boundary(SCHEMA, "/$defs/RegisterProtocolRequest", payload)


def validate_amendment(payload: Any) -> None:
    validate_boundary(SCHEMA, "/$defs/ProtocolAmendmentRequest", payload)


def validate_edge(payload: Any) -> None:
    validate_boundary(SCHEMA, "/$defs/CreateEdgeRequest", payload)


def validate_experiment(payload: Any) -> None:
    validate_boundary(SCHEMA, "/$defs/ExperimentRunRequest", payload)


def validate_receipt(payload: Any) -> None:
    validate_boundary(SCHEMA, "/$defs/ResolutionReceiptRequest", payload)


def _contains_secret_like_value(value: Any) -> bool:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False).lower()
    return any(marker in raw for marker in SECRETS_RE)


def _public_summary(object_type: str, payload: dict[str, Any], lane: str) -> dict[str, Any]:
    if lane in {"SEALED", "RESTRICTED"}:
        return {
            "object_type": object_type,
            "commitment_hash": payload.get("commitment_hash"),
            "plaintext_disclosed": False,
        }
    title = payload.get("title") or payload.get("question") or payload.get("name")
    return {
        "object_type": object_type,
        "title": str(title)[:200] if title is not None else None,
        "plaintext_disclosed": True,
    }


def _assert_lane(payload: dict[str, Any]) -> None:
    lane = payload["visibility_lane"]
    rights = payload["rights_status"]
    if _contains_secret_like_value(payload.get("payload", {})):
        raise KnowledgeLedgerViolation("Knowledge objects must not contain secrets or private CoT.")
    if lane == "OPEN" and (rights != OPEN_LICENSE_RIGHTS or not payload.get("license_id")):
        raise KnowledgeLedgerViolation("OPEN publication requires explicit rights and license.")
    if lane in {"SEALED", "RESTRICTED"}:
        object_payload = payload.get("payload", {})
        if object_payload.get("plaintext") or object_payload.get("content"):
            raise KnowledgeLedgerViolation(f"{lane} objects accept commitments, not plaintext.")
        if not object_payload.get("commitment_hash"):
            raise KnowledgeLedgerViolation(f"{lane} objects require a commitment_hash.")
    if lane == "RESTRICTED" and rights != "restricted":
        raise KnowledgeLedgerViolation("RESTRICTED objects require restricted rights status.")


def object_view(row: MagnaKnowledgeObject, *, reveal_payload: bool = False) -> dict[str, Any]:
    lane = row.visibility_lane
    can_reveal = reveal_payload or lane == "OPEN"
    return {
        "object_id": row.object_id,
        "object_type": row.object_type,
        "object_version": row.object_version,
        "world_instance_id": row.world_instance_id,
        "world_id": row.world_id,
        "challenge_id": row.challenge_id,
        "proposal_id": row.proposal_id,
        "author_agent_id": row.author_agent_id,
        "author_agent_version_id": row.author_agent_version_id,
        "beneficial_controller_id": row.beneficial_controller_id,
        "visibility_lane": lane,
        "safety_classification": row.safety_classification,
        "rights_status": row.rights_status,
        "license_id": row.license_id,
        "payload": row.payload if can_reveal else None,
        "public_summary": row.public_summary,
        "canonical_content_hash": row.canonical_content_hash,
        "parent_hashes": row.parent_hashes,
        "constitution_hash": row.constitution_hash,
        "charter_hash": row.charter_hash,
        "state": row.state,
        "maturity": row.maturity,
        "frozen_hash": row.frozen_hash,
        "supersedes_object_id": row.supersedes_object_id,
        "untrusted_remote": True,
        "created_at": row.created_at.isoformat().replace("+00:00", "Z"),
    }


def edge_view(row: MagnaKnowledgeEdge) -> dict[str, Any]:
    return {
        "edge_id": row.edge_id,
        "source_object_id": row.source_object_id,
        "target_object_id": row.target_object_id,
        "relation_type": row.relation_type,
        "actor_agent_id": row.actor_agent_id,
        "actor_agent_version_id": row.actor_agent_version_id,
        "payload": row.payload,
        "canonical_content_hash": row.canonical_content_hash,
        "created_at": row.created_at.isoformat().replace("+00:00", "Z"),
        "retracted_at": row.retracted_at.isoformat().replace("+00:00", "Z")
        if row.retracted_at
        else None,
    }


async def _charter_hash(session: AsyncSession, world_id: str | None) -> str | None:
    if not world_id:
        return None
    charter = await current_charter(session, world_id)
    return charter.content_hash


async def _parent_hashes(session: AsyncSession, parent_ids: list[str]) -> list[str]:
    hashes = []
    for parent_id in parent_ids:
        parent = await session.get(MagnaKnowledgeObject, parent_id)
        if parent is None:
            raise NotFound("Parent knowledge object not found.")
        hashes.append(parent.canonical_content_hash)
    return hashes


async def create_object(
    session: AsyncSession,
    *,
    agent: Agent,
    payload: dict[str, Any],
    trace_id: str | None = None,
) -> MagnaKnowledgeObject:
    validate_create_object(payload)
    _assert_lane(payload)
    existing = (
        await session.execute(
            select(MagnaKnowledgeObject).where(
                MagnaKnowledgeObject.author_agent_id == agent.agent_id,
                MagnaKnowledgeObject.idempotency_key == payload["idempotency_key"],
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    constitution = await current_constitution(session)
    parent_ids = payload.get("parent_object_ids") or []
    parent_hashes = await _parent_hashes(session, parent_ids)
    now = now_utc()
    canonical_body = {
        "object_type": payload["object_type"],
        "payload": payload["payload"],
        "parents": parent_hashes,
        "lane": payload["visibility_lane"],
        "rights": payload["rights_status"],
        "license_id": payload.get("license_id"),
        "constitution_hash": constitution.content_hash,
    }
    content_hash = canonical_json_hash(canonical_body, domain="agora.magna.knowledge.object.v1")
    row = MagnaKnowledgeObject(
        object_id=new_knowledge_object_id(),
        object_type=payload["object_type"],
        object_version=1,
        world_instance_id=get_settings().world_instance_id,
        world_id=payload.get("world_id"),
        challenge_id=payload.get("challenge_id"),
        proposal_id=payload.get("proposal_id"),
        author_agent_id=agent.agent_id,
        author_agent_version_id=agent.current_version_id,
        beneficial_controller_id=payload.get("beneficial_controller_id") or agent.agent_id,
        visibility_lane=payload["visibility_lane"],
        safety_classification=payload.get("safety_classification", "D0_PUBLIC_METADATA"),
        rights_status=payload["rights_status"],
        license_id=payload.get("license_id"),
        payload=payload["payload"],
        public_summary=_public_summary(
            payload["object_type"],
            payload["payload"],
            payload["visibility_lane"],
        ),
        canonical_content_hash=content_hash,
        parent_hashes=parent_hashes,
        constitution_hash=constitution.content_hash,
        charter_hash=await _charter_hash(session, payload.get("world_id")),
        rule_evaluation_receipt_id=None,
        state=payload.get("state", "PROPOSED"),
        maturity=payload.get("maturity", "exploratory"),
        frozen_hash=content_hash if payload["object_type"] == "registered_protocol" else None,
        supersedes_object_id=payload.get("supersedes_object_id"),
        idempotency_key=payload["idempotency_key"],
        created_at=now,
    )
    session.add(row)
    await session.flush()
    await append_event(
        session,
        event_type=f"knowledge.{payload['object_type']}.created",
        actor={"agent_id": agent.agent_id, "agent_version_id": agent.current_version_id},
        payload={
            "object_id": row.object_id,
            "object_type": row.object_type,
            "content_hash": row.canonical_content_hash,
            "visibility_lane": row.visibility_lane,
        },
        trace_id=trace_id,
    )
    return row


async def register_protocol(
    session: AsyncSession, *, agent: Agent, payload: dict[str, Any], trace_id: str | None = None
) -> MagnaKnowledgeObject:
    validate_register_protocol(payload)
    body = {
        **payload,
        "protocol_kind": payload["confirmatory_or_exploratory"],
        "frozen": True,
        "retrospective_reclassification_allowed": False,
    }
    create_payload = {
        "object_type": "registered_protocol",
        "world_id": "science",
        "visibility_lane": payload["visibility_lane"],
        "rights_status": payload["rights_status"],
        "payload": body,
        "idempotency_key": payload["idempotency_key"],
    }
    for key in ("license_id", "beneficial_controller_id"):
        if payload.get(key) is not None:
            create_payload[key] = payload[key]
    return await create_object(
        session,
        agent=agent,
        payload=create_payload,
        trace_id=trace_id,
    )


async def amend_protocol(
    session: AsyncSession,
    *,
    protocol_id: str,
    agent: Agent,
    payload: dict[str, Any],
    trace_id: str | None = None,
) -> MagnaKnowledgeObject:
    validate_amendment(payload)
    protocol = await session.get(MagnaKnowledgeObject, protocol_id)
    if protocol is None or protocol.object_type != "registered_protocol":
        raise NotFound("Registered protocol not found.")
    amendment = await create_object(
        session,
        agent=agent,
        payload={
            "object_type": "protocol_amendment",
            "world_id": protocol.world_id,
            "visibility_lane": protocol.visibility_lane,
            "rights_status": protocol.rights_status,
            "license_id": protocol.license_id,
            "beneficial_controller_id": protocol.beneficial_controller_id,
            "payload": {
                "registered_protocol_id": protocol.object_id,
                "registered_protocol_frozen_hash": protocol.frozen_hash,
                "justification": payload["justification"],
                "changes": payload["changes"],
                "affected_result_ids": payload.get("affected_result_ids", []),
                "rewrites_original": False,
            },
            "parent_object_ids": [protocol.object_id],
            "idempotency_key": payload["idempotency_key"],
        },
        trace_id=trace_id,
    )
    await create_edge(
        session,
        agent=agent,
        payload={
            "source_object_id": amendment.object_id,
            "target_object_id": protocol.object_id,
            "relation_type": "was_derived_from",
            "payload": {"amends_without_rewriting": True},
            "idempotency_key": f"{payload['idempotency_key']}:edge",
        },
        trace_id=trace_id,
    )
    return amendment


async def _path_exists(
    session: AsyncSession, start_id: str, target_id: str, *, depth_limit: int = 64
) -> bool:
    frontier = [start_id]
    seen = {start_id}
    for _ in range(depth_limit):
        if not frontier:
            return False
        rows = (
            await session.execute(
                select(MagnaKnowledgeEdge.target_object_id).where(
                    MagnaKnowledgeEdge.source_object_id.in_(frontier),
                    MagnaKnowledgeEdge.retracted_at.is_(None),
                    MagnaKnowledgeEdge.relation_type.in_(GRAPH_RELATIONS),
                )
            )
        ).scalars().all()
        if target_id in rows:
            return True
        frontier = [row for row in rows if row not in seen]
        seen.update(frontier)
    raise KnowledgeLedgerViolation("Provenance graph traversal exceeded safe depth.")


async def create_edge(
    session: AsyncSession,
    *,
    agent: Agent,
    payload: dict[str, Any],
    trace_id: str | None = None,
) -> MagnaKnowledgeEdge:
    validate_edge(payload)
    if payload["source_object_id"] == payload["target_object_id"]:
        raise KnowledgeLedgerViolation("Self-relations are not allowed.")
    source = await session.get(MagnaKnowledgeObject, payload["source_object_id"])
    target = await session.get(MagnaKnowledgeObject, payload["target_object_id"])
    if source is None or target is None:
        raise NotFound("Knowledge object not found.")
    existing = (
        await session.execute(
            select(MagnaKnowledgeEdge).where(
                MagnaKnowledgeEdge.actor_agent_id == agent.agent_id,
                MagnaKnowledgeEdge.idempotency_key == payload["idempotency_key"],
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    relation = payload["relation_type"]
    if relation in GRAPH_RELATIONS and await _path_exists(
        session, payload["target_object_id"], payload["source_object_id"]
    ):
        raise Conflict("Provenance edge would create a cycle.")
    body = {
        "source": source.canonical_content_hash,
        "target": target.canonical_content_hash,
        "relation_type": relation,
        "payload": payload.get("payload", {}),
    }
    row = MagnaKnowledgeEdge(
        edge_id=new_knowledge_edge_id(),
        source_object_id=source.object_id,
        target_object_id=target.object_id,
        relation_type=relation,
        actor_agent_id=agent.agent_id,
        actor_agent_version_id=agent.current_version_id,
        payload=payload.get("payload", {}),
        canonical_content_hash=canonical_json_hash(body, domain="agora.magna.knowledge.edge.v1"),
        idempotency_key=payload["idempotency_key"],
        created_at=now_utc(),
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise Conflict("Duplicate knowledge edge assertion.") from exc
    await append_event(
        session,
        event_type="knowledge.provenance.edge_created",
        actor={"agent_id": agent.agent_id, "agent_version_id": agent.current_version_id},
        payload={"edge_id": row.edge_id, "relation_type": row.relation_type},
        trace_id=trace_id,
    )
    return row


async def record_experiment(
    session: AsyncSession, *, agent: Agent, payload: dict[str, Any], trace_id: str | None = None
) -> MagnaKnowledgeObject:
    validate_experiment(payload)
    protocol = await session.get(MagnaKnowledgeObject, payload["registered_protocol_id"])
    if protocol is None or protocol.object_type != "registered_protocol":
        raise NotFound("Registered protocol not found.")
    body = {
        **payload,
        "registered_protocol_frozen_hash": protocol.frozen_hash,
        "no_private_prompts_or_cot": True,
    }
    row = await create_object(
        session,
        agent=agent,
        payload={
            "object_type": "experiment_run",
            "world_id": protocol.world_id,
            "visibility_lane": protocol.visibility_lane,
            "rights_status": protocol.rights_status,
            "license_id": protocol.license_id,
            "beneficial_controller_id": protocol.beneficial_controller_id,
            "payload": body,
            "parent_object_ids": [protocol.object_id],
            "idempotency_key": payload["idempotency_key"],
            "state": "UNDER_TEST",
        },
        trace_id=trace_id,
    )
    await create_edge(
        session,
        agent=agent,
        payload={
            "source_object_id": row.object_id,
            "target_object_id": protocol.object_id,
            "relation_type": "was_generated_by",
            "payload": {"run_status": payload["run_status"]},
            "idempotency_key": f"{payload['idempotency_key']}:protocol-edge",
        },
        trace_id=trace_id,
    )
    return row


async def verify_capsule_fixture(
    session: AsyncSession, *, capsule_id: str, agent: Agent, trace_id: str | None = None
) -> dict[str, Any]:
    capsule = await session.get(MagnaKnowledgeObject, capsule_id)
    if capsule is None or capsule.object_type != "reproducibility_capsule":
        raise NotFound("Reproducibility capsule not found.")
    payload = capsule.payload
    expected = payload.get("expected_output_hash")
    fixture = payload.get("fixture_input")
    if not expected or fixture is None:
        quality = "incomplete"
        verified = False
    else:
        observed = hashlib.sha256(str(fixture).encode()).hexdigest()
        verified = observed == expected
        quality = "reproduced_same_environment" if verified else "incomplete"
    await append_event(
        session,
        event_type="knowledge.reproducibility_capsule.verified",
        actor={"agent_id": agent.agent_id, "agent_version_id": agent.current_version_id},
        payload={"object_id": capsule.object_id, "verified": verified, "quality": quality},
        trace_id=trace_id,
    )
    return {"object_id": capsule.object_id, "verified": verified, "quality": quality}


async def resolve_epistemic_state(
    session: AsyncSession, *, agent: Agent, payload: dict[str, Any], trace_id: str | None = None
) -> MagnaResolutionReceipt:
    validate_receipt(payload)
    existing = (
        await session.execute(
            select(MagnaResolutionReceipt).where(
                MagnaResolutionReceipt.created_by_agent_id == agent.agent_id,
                MagnaResolutionReceipt.idempotency_key == payload["idempotency_key"],
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    outcome = await session.get(MagnaKnowledgeObject, payload["outcome_id"])
    protocol = await session.get(MagnaKnowledgeObject, payload["registered_protocol_id"])
    if outcome is None or protocol is None:
        raise NotFound("Outcome or registered protocol not found.")
    evidence_ids = payload["evidence_object_ids"]
    evidence = (
        await session.execute(
            select(MagnaKnowledgeObject).where(MagnaKnowledgeObject.object_id.in_(evidence_ids))
        )
    ).scalars().all()
    if len(evidence) != len(set(evidence_ids)):
        raise NotFound("Evidence object not found.")
    requested = payload["requested_state"]
    controllers = {row.beneficial_controller_id for row in evidence}
    replications = payload.get("replication_object_ids") or []
    decision = "accepted"
    reason_codes = ["receipt_inputs_valid", "no_payment_in_sprint_03"]
    if requested == "REPLICATED":
        replication_rows = (
            await session.execute(
                select(MagnaKnowledgeObject).where(MagnaKnowledgeObject.object_id.in_(replications))
            )
        ).scalars().all()
        controllers |= {row.beneficial_controller_id for row in replication_rows}
        if len(controllers) < 2:
            decision = "rejected"
            reason_codes.append("independent_controller_requirement_not_met")
    if requested in {
        "SUPPORTED_ONCE",
        "RESOLVED_VERIFIED",
        "REFUTED",
        "INCONCLUSIVE",
        "CONTESTED",
    } and not evidence:
        decision = "rejected"
        reason_codes.append("evidence_required")
    receipt_body = {
        "challenge_id": payload["challenge_id"],
        "outcome_hash": outcome.canonical_content_hash,
        "registered_protocol_hash": protocol.canonical_content_hash,
        "requested_state": requested,
        "decision": decision,
        "reason_codes": reason_codes,
        "evidence_hashes": [row.canonical_content_hash for row in evidence],
        "replication_object_ids": replications,
        "review_object_ids": payload.get("review_object_ids", []),
        "unresolved_dissent_ids": payload.get("unresolved_dissent_ids", []),
        "independent_controller_count": len(controllers),
        "payment_eligible": False,
    }
    content_hash = canonical_json_hash(
        receipt_body, domain="agora.magna.knowledge.resolution_receipt.v1"
    )
    row = MagnaResolutionReceipt(
        receipt_id=new_resolution_receipt_id(),
        challenge_id=payload["challenge_id"],
        outcome_id=outcome.object_id,
        registered_protocol_id=protocol.object_id,
        requested_state=requested,
        decision=decision,
        reason_codes=reason_codes,
        evidence_object_ids=evidence_ids,
        replication_object_ids=replications,
        review_object_ids=payload.get("review_object_ids", []),
        unresolved_dissent_ids=payload.get("unresolved_dissent_ids", []),
        independence_receipt={"independent_controller_count": len(controllers)},
        constitution_hash=outcome.constitution_hash,
        charter_hash=outcome.charter_hash,
        content_hash=content_hash,
        payment_eligible=False,
        idempotency_key=payload["idempotency_key"],
        created_by_agent_id=agent.agent_id,
        created_at=now_utc(),
    )
    session.add(row)
    await session.flush()
    if decision == "accepted":
        outcome.state = requested
    await append_event(
        session,
        event_type="knowledge.resolution.receipt_created",
        actor={"agent_id": agent.agent_id, "agent_version_id": agent.current_version_id},
        payload={
            "receipt_id": row.receipt_id,
            "decision": decision,
            "requested_state": requested,
            "payment_eligible": False,
        },
        trace_id=trace_id,
    )
    return row


async def get_lineage(
    session: AsyncSession, *, object_id: str, depth: int = 1, limit: int = 100
) -> dict[str, Any]:
    if depth not in {1, 2}:
        raise ValidationFailed("Lineage depth must be 1 or 2.")
    root = await session.get(MagnaKnowledgeObject, object_id)
    if root is None:
        raise NotFound("Knowledge object not found.")
    seen_nodes = {object_id}
    frontier = {object_id}
    edges: list[MagnaKnowledgeEdge] = []
    for _ in range(depth):
        rows = (
            await session.execute(
                select(MagnaKnowledgeEdge).where(
                    or_(
                        MagnaKnowledgeEdge.source_object_id.in_(frontier),
                        MagnaKnowledgeEdge.target_object_id.in_(frontier),
                    ),
                    MagnaKnowledgeEdge.retracted_at.is_(None),
                ).limit(limit)
            )
        ).scalars().all()
        edges.extend(rows)
        for edge in rows:
            seen_nodes.add(edge.source_object_id)
            seen_nodes.add(edge.target_object_id)
        frontier = seen_nodes - frontier
        if len(edges) >= limit:
            break
    nodes = (
        await session.execute(
            select(MagnaKnowledgeObject).where(MagnaKnowledgeObject.object_id.in_(seen_nodes))
        )
    ).scalars().all()
    return {
        "root_object_id": object_id,
        "depth": depth,
        "limit": limit,
        "truncated": len(edges) >= limit,
        "nodes": [object_view(row) for row in nodes],
        "edges": [edge_view(row) for row in edges[:limit]],
    }


def _merkle_parent(left: str, right: str) -> str:
    return hashlib.sha256(bytes.fromhex(left) + bytes.fromhex(right)).hexdigest()


def merkle_root(leaves: list[str]) -> str:
    if not leaves:
        raise ValidationFailed("Cannot create empty Merkle batch.")
    layer = leaves[:]
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        layer = [_merkle_parent(layer[i], layer[i + 1]) for i in range(0, len(layer), 2)]
    return layer[0]


async def create_merkle_batch(
    session: AsyncSession, *, first_sequence: int, last_sequence: int, agent: Agent | None = None
) -> MagnaMerkleBatch:
    if first_sequence > last_sequence:
        raise ValidationFailed("Invalid Merkle sequence window.")
    rows = (
        await session.execute(
            select(MagnaKnowledgeObject)
            .order_by(MagnaKnowledgeObject.created_at, MagnaKnowledgeObject.object_id)
            .offset(first_sequence - 1)
            .limit(last_sequence - first_sequence + 1)
        )
    ).scalars().all()
    if len(rows) != last_sequence - first_sequence + 1:
        raise ValidationFailed("Merkle window has missing ledger objects.")
    leaves = [
        canonical_json_hash(
            {
                "sequence": first_sequence + idx,
                "object_id": row.object_id,
                "content_hash": row.canonical_content_hash,
                "world_instance_id": row.world_instance_id,
            },
            domain="agora.magna.knowledge.merkle_leaf.v1",
        )
        for idx, row in enumerate(rows)
    ]
    batch = MagnaMerkleBatch(
        batch_id=new_merkle_batch_id(),
        world_instance_id=get_settings().world_instance_id,
        first_sequence=first_sequence,
        last_sequence=last_sequence,
        leaf_count=len(leaves),
        merkle_root=merkle_root(leaves),
        algorithm="sha256-binary-tree",
        previous_batch_hash=None,
        leaves=leaves,
        created_by_agent_id=agent.agent_id if agent else None,
        created_at=now_utc(),
    )
    session.add(batch)
    await session.flush()
    return batch
