"""Live Knowledge Fabric domain (Sprint 07).

This module intentionally does not expose a generic URL fetcher. Each adapter
is selected from `knowledge_sources`, whose rows contain fixed allowed hosts and
source policy. Sprint 07 uses deterministic local adapters so CI and local dev
need no external credentials, while preserving the trust boundary where future
real upstream clients will live.
"""

import asyncio
import hashlib
import json
import re
from datetime import timedelta
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.boundary import validate_boundary
from agora_api.claims_service import attach_evidence, evidence_view
from agora_api.errors import AgoraError, NotFound
from agora_api.events import append_event, now_utc
from agora_api.ids import new_evidence_id, new_knowledge_snapshot_id, new_world_pulse_event_id
from agora_api.models import (
    Claim,
    Evidence,
    KnowledgeSnapshot,
    KnowledgeSource,
    WorldPulseEvent,
    WorldPulseSource,
)

WORLD_PULSE_SPACE_ID = "spc_00000000000000000000PULSE"
URL_OR_INTERNAL_RE = re.compile(
    r"(https?://|localhost|127\.|0\.0\.0\.0|::1|169\.254\.169\.254|"
    r"metadata\.google\.internal|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)",
    re.IGNORECASE,
)
_locks: dict[str, asyncio.Lock] = {}


class KnowledgePolicyViolation(AgoraError):
    status_code = 422
    code = "knowledge_policy_violation"


class KnowledgeSourceUnavailable(AgoraError):
    status_code = 503
    code = "knowledge_source_unavailable"


def validate_query_request(payload: Any) -> None:
    validate_boundary("knowledge.schema.json", "/$defs/QueryRequest", payload)


def validate_snapshot_evidence_request(payload: Any) -> None:
    validate_boundary("knowledge.schema.json", "/$defs/SnapshotEvidenceRequest", payload)


def source_view(source: KnowledgeSource) -> dict[str, Any]:
    return {
        "source_id": source.source_id,
        "adapter_id": source.adapter_id,
        "name": source.name,
        "domain": source.domain,
        "base_url": source.base_url,
        "allowed_hosts": source.allowed_hosts,
        "capabilities": source.capabilities,
        "freshness_contract": source.freshness_contract,
        "license_terms": source.license_terms,
        "ttl_seconds": source.ttl_seconds,
        "enabled": source.enabled,
        "upstream_call_count": source.upstream_call_count,
        "cache_hit_count": source.cache_hit_count,
    }


def snapshot_view(snapshot: KnowledgeSnapshot) -> dict[str, Any]:
    return {
        "snapshot_id": snapshot.snapshot_id,
        "source_id": snapshot.source_id,
        "query_hash": snapshot.query_hash,
        "normalized_query": snapshot.normalized_query,
        "query": snapshot.query,
        "result": snapshot.result,
        "raw_metadata": snapshot.raw_metadata,
        "raw_locator": snapshot.raw_locator,
        "freshness_contract": snapshot.freshness_contract,
        "observed_at": snapshot.observed_at.isoformat(),
        "source_updated_at": (
            snapshot.source_updated_at.isoformat() if snapshot.source_updated_at else None
        ),
        "content_hash": snapshot.content_hash,
        "license_terms": snapshot.license_terms,
        "expires_at": snapshot.expires_at.isoformat(),
        "trust": "agora_verified_snapshot",
        "untrusted_remote": True,
    }


def pulse_view(event: WorldPulseEvent) -> dict[str, Any]:
    return {
        "pulse_event_id": event.pulse_event_id,
        "cluster_key": event.cluster_key,
        "title": event.title,
        "summary": event.summary,
        "freshness_contract": event.freshness_contract,
        "source_count": event.source_count,
        "latest_snapshot_id": event.latest_snapshot_id,
        "created_at": event.created_at.isoformat(),
        "updated_at": event.updated_at.isoformat(),
    }


def normalize_query(query: str) -> str:
    normalized = " ".join(query.strip().lower().split())
    if URL_OR_INTERNAL_RE.search(normalized):
        raise KnowledgePolicyViolation(
            "Knowledge queries are not URLs; AGORA does not perform arbitrary fetches."
        )
    return normalized


def query_hash(source_id: str, normalized_query: str, as_of: str | None) -> str:
    payload = {"source_id": source_id, "query": normalized_query, "as_of": as_of}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def content_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


async def resolve_source(session: AsyncSession, source_ref: str) -> KnowledgeSource:
    query = select(KnowledgeSource).where(
        (KnowledgeSource.source_id == source_ref) | (KnowledgeSource.adapter_id == source_ref)
    )
    source = (await session.execute(query)).scalar_one_or_none()
    if source is None:
        raise NotFound("Knowledge source not found.")
    if not source.enabled:
        raise KnowledgeSourceUnavailable("Knowledge source is disabled.")
    if source.circuit_open_until and source.circuit_open_until > now_utc():
        raise KnowledgeSourceUnavailable("Knowledge source circuit breaker is open.")
    return source


def adapter_result(source: KnowledgeSource, normalized_query: str, limit: int) -> dict[str, Any]:
    """Deterministic adapter output with source-specific metadata.

    It simulates current public-source metadata without external network I/O.
    The output is deliberately small to avoid article/dataset replication.
    """
    kind = source.adapter_id
    title = f"{source.name}: {normalized_query.title()}"
    locator_digest = hashlib.sha256(normalized_query.encode()).hexdigest()[:12]
    items = [
        {
            "title": title,
            "source": source.name,
            "locator": f"{source.base_url}/agora-snapshot/{locator_digest}",
            "excerpt": (
                f"Bounded metadata result for '{normalized_query}' from {source.name}. "
                "Full source content is not replicated."
            )[:240],
        }
    ]
    if kind in {"fred", "world_bank"}:
        items[0]["vintage"] = "source-defined-current"
        items[0]["series"] = normalized_query.upper()[:24]
    if kind in {"clinvar", "ensembl"}:
        items[0]["gene_or_variant"] = normalized_query.upper()[:32]
    if kind in {"gdelt_world_pulse", "nasa_public"}:
        items[0]["cluster_key"] = hashlib.sha256(normalized_query.encode()).hexdigest()
        items[0]["event_title"] = normalized_query.title()
    return {
        "schema_version": "1.0",
        "source": source.adapter_id,
        "query": normalized_query,
        "items": items[:limit],
        "freshness_contract": source.freshness_contract,
        "verification": "adapter_metadata_snapshot",
    }


async def get_cached_snapshot(
    session: AsyncSession, *, source_id: str, qhash: str
) -> KnowledgeSnapshot | None:
    snapshot = (
        await session.execute(
            select(KnowledgeSnapshot)
            .where(
                KnowledgeSnapshot.source_id == source_id,
                KnowledgeSnapshot.query_hash == qhash,
                KnowledgeSnapshot.expires_at > now_utc(),
            )
            .order_by(desc(KnowledgeSnapshot.observed_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    return snapshot


async def search(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
    trace_id: str | None,
) -> KnowledgeSnapshot:
    validate_query_request(payload)
    source = await resolve_source(session, payload["source_id"])
    normalized = normalize_query(payload["query"])
    as_of = payload.get("as_of")
    qhash = query_hash(source.source_id, normalized, as_of)
    lock_key = f"{source.source_id}:{qhash}"
    lock = _locks.setdefault(lock_key, asyncio.Lock())

    async with lock:
        if not payload.get("force_refresh"):
            cached = await get_cached_snapshot(session, source_id=source.source_id, qhash=qhash)
            if cached is not None:
                source.cache_hit_count += 1
                source.updated_at = now_utc()
                await session.flush()
                return cached

        now = now_utc()
        source.upstream_call_count += 1
        source.updated_at = now
        result = adapter_result(source, normalized, int(payload.get("limit") or 10))
        chash = content_hash(result)
        snapshot = KnowledgeSnapshot(
            snapshot_id=new_knowledge_snapshot_id(),
            source_id=source.source_id,
            query_hash=qhash,
            normalized_query=normalized,
            query={"query": payload["query"], "as_of": as_of, "limit": payload.get("limit", 10)},
            result=result,
            raw_metadata={
                "adapter_id": source.adapter_id,
                "allowed_hosts": source.allowed_hosts,
                "coalesced": True,
            },
            raw_locator=f"{source.base_url}/search",
            freshness_contract=source.freshness_contract,
            observed_at=now,
            source_updated_at=now if source.freshness_contract != "HISTORICAL" else None,
            content_hash=chash,
            license_terms=source.license_terms,
            expires_at=now + timedelta(seconds=source.ttl_seconds),
            created_at=now,
        )
        session.add(snapshot)
        await session.flush()
        await append_event(
            session,
            event_type="knowledge.snapshot_created",
            actor={"agent_id": "agt_00000000000000000000000000"},
            payload={
                "snapshot_id": snapshot.snapshot_id,
                "source_id": source.source_id,
                "query_hash": qhash,
                "content_hash": chash,
            },
            trace_id=trace_id,
        )
        if source.domain in {"world_pulse", "space_science"}:
            await upsert_world_pulse(session, snapshot=snapshot, source=source, trace_id=trace_id)
        # Commit before releasing the per-query lock so concurrent identical
        # requests observe this snapshot through the persistent cache instead
        # of issuing duplicate upstream adapter work.
        await session.commit()
        return snapshot


async def upsert_world_pulse(
    session: AsyncSession,
    *,
    snapshot: KnowledgeSnapshot,
    source: KnowledgeSource,
    trace_id: str | None,
) -> WorldPulseEvent:
    first_item = (snapshot.result.get("items") or [{}])[0]
    cluster_key = str(first_item.get("cluster_key") or snapshot.query_hash)
    existing = (
        await session.execute(
            select(WorldPulseEvent).where(WorldPulseEvent.cluster_key == cluster_key)
        )
    ).scalar_one_or_none()
    now = now_utc()
    if existing is None:
        existing = WorldPulseEvent(
            pulse_event_id=new_world_pulse_event_id(),
            cluster_key=cluster_key,
            title=str(first_item.get("event_title") or first_item.get("title") or "World event"),
            summary=str(first_item.get("excerpt") or "Clustered public-source event."),
            freshness_contract=source.freshness_contract,
            source_count=1,
            latest_snapshot_id=snapshot.snapshot_id,
            created_at=now,
            updated_at=now,
        )
        session.add(existing)
        await session.flush()
    else:
        existing.latest_snapshot_id = snapshot.snapshot_id
        existing.updated_at = now
        if source.freshness_contract == "NEAR_REALTIME":
            existing.freshness_contract = source.freshness_contract
    link = await session.get(WorldPulseSource, (existing.pulse_event_id, snapshot.snapshot_id))
    if link is None:
        session.add(
            WorldPulseSource(
                pulse_event_id=existing.pulse_event_id,
                snapshot_id=snapshot.snapshot_id,
                source_id=source.source_id,
                created_at=now,
            )
        )
        rows = (
            await session.execute(
                select(WorldPulseSource.source_id)
                .where(WorldPulseSource.pulse_event_id == existing.pulse_event_id)
                .distinct()
            )
        ).all()
        existing.source_count = len(rows) + (
            0 if any(row[0] == source.source_id for row in rows) else 1
        )
    await append_event(
        session,
        event_type="world_pulse.event_clustered",
        actor={"agent_id": "agt_00000000000000000000000000"},
        payload={
            "pulse_event_id": existing.pulse_event_id,
            "snapshot_id": snapshot.snapshot_id,
            "source_count": existing.source_count,
        },
        trace_id=trace_id,
    )
    return existing


async def create_verified_evidence_from_snapshot(
    session: AsyncSession,
    *,
    snapshot: KnowledgeSnapshot,
    agent_id: str,
    role: str,
    claim_id: str | None,
    trace_id: str | None,
) -> dict[str, Any]:
    first_item = (snapshot.result.get("items") or [{}])[0]
    evidence = Evidence(
        evidence_id=new_evidence_id(),
        source_type="other",
        locator=f"knowledge://snapshot/{snapshot.snapshot_id}",
        provenance_level="agora_verified_snapshot",
        title=str(first_item.get("title") or snapshot.normalized_query)[:300],
        excerpt=str(first_item.get("excerpt") or "")[:600],
        publisher=str(snapshot.result.get("source") or snapshot.source_id)[:200],
        content_hash=snapshot.content_hash,
        observed_at=snapshot.observed_at,
        published_at=snapshot.source_updated_at,
        created_by_agent_id=agent_id,
        created_at=now_utc(),
    )
    session.add(evidence)
    await session.flush()
    attachment = None
    if claim_id:
        claim = await session.get(Claim, claim_id)
        if claim is None:
            raise NotFound("Claim not found.")
        attachment = await attach_evidence(
            session,
            claim=claim,
            evidence=evidence,
            role=role,
            agent_id=agent_id,
            trace_id=trace_id,
        )
    await append_event(
        session,
        event_type="knowledge.snapshot_evidence_created",
        actor={"agent_id": agent_id},
        payload={
            "snapshot_id": snapshot.snapshot_id,
            "evidence_id": evidence.evidence_id,
            "claim_id": claim_id,
        },
        trace_id=trace_id,
    )
    return {
        **evidence_view(evidence),
        "snapshot_id": snapshot.snapshot_id,
        "attachment": {
            "claim_id": attachment.claim_id,
            "role": attachment.role,
        } if attachment else None,
    }
