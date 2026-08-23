"""Artifact domain: publication, provenance, reviews, revision loop
(S5-T13..T20, ADR-0027/0028).

Server-side responsibilities only. The ArtifactStore boundary (streaming,
hashing, byte caps) lives in `artifact_store.py`; the Bridge-side local
publication boundary (secret-file guardrails, no recursive upload, symlink
prevention, LocalPolicyEngine gating) lives in the Bridge, not here — this
module never sees local filesystem paths, only already-streamed bytes.
"""

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.boundary import validate_boundary
from agora_api.errors import AgoraError, NotFound, ValidationFailed
from agora_api.events import append_event, now_utc
from agora_api.ids import new_artifact_id, new_artifact_version_id, new_review_id
from agora_api.models import Artifact, ArtifactReview, ArtifactVersion, MissionTask

REVIEW_VERDICTS = frozenset({"approve", "needs_changes", "reject"})


class VersionNotPublishable(AgoraError):
    status_code = 409
    code = "version_not_publishable"


class DuplicateReview(AgoraError):
    status_code = 409
    code = "duplicate_review"


def validate_create_artifact(payload: Any) -> None:
    validate_boundary("artifacts.schema.json", "/$defs/CreateArtifactRequest", payload)


def validate_publish_metadata(payload: Any) -> None:
    validate_boundary("artifacts.schema.json", "/$defs/PublishVersionMetadata", payload)


def validate_create_review(payload: Any) -> None:
    validate_boundary("artifacts.schema.json", "/$defs/CreateReviewRequest", payload)


def artifact_view(artifact: Artifact) -> dict[str, Any]:
    return {
        "artifact_id": artifact.artifact_id,
        "title": artifact.title,
        "description": artifact.description,
        "artifact_type": artifact.artifact_type,
        "visibility": artifact.visibility,
        "created_by_agent_id": artifact.created_by_agent_id,
        "latest_version_number": artifact.latest_version_number,
        "created_at": artifact.created_at.isoformat(),
    }


def version_view(version: ArtifactVersion) -> dict[str, Any]:
    return {
        "artifact_version_id": version.artifact_version_id,
        "artifact_id": version.artifact_id,
        "version_number": version.version_number,
        "state": version.state,
        "created_by_agent_id": version.created_by_agent_id,
        "content_hash": version.content_hash,
        "content_size": version.content_size,
        "media_type": version.media_type,
        "display_filename": version.display_filename,
        "provenance_manifest": version.provenance_manifest,
        "provenance_hash": version.provenance_hash,
        "created_at": version.created_at.isoformat(),
        "published_at": version.published_at.isoformat() if version.published_at else None,
    }


def review_view(review: ArtifactReview) -> dict[str, Any]:
    return {
        "review_id": review.review_id,
        "artifact_version_id": review.artifact_version_id,
        "reviewer_agent_id": review.reviewer_agent_id,
        "verdict": review.verdict,
        "comment": review.comment,
        "scores": review.scores,
        "is_self_review": review.is_self_review,
        "created_at": review.created_at.isoformat(),
    }


async def create_artifact(
    session: AsyncSession, *, agent_id: str, payload: dict[str, Any], trace_id: str | None
) -> Artifact:
    artifact = Artifact(
        artifact_id=new_artifact_id(),
        title=payload["title"],
        description=payload.get("description"),
        artifact_type=payload["artifact_type"],
        visibility=payload.get("visibility", "public"),
        created_by_agent_id=agent_id,
        latest_version_number=0,
        created_at=now_utc(),
    )
    session.add(artifact)
    await append_event(
        session,
        event_type="artifact.created",
        actor={"agent_id": agent_id},
        payload={"artifact_id": artifact.artifact_id, "artifact_type": artifact.artifact_type},
        trace_id=trace_id,
    )
    return artifact


def canonical_provenance_json(manifest: dict[str, Any]) -> bytes:
    """Deterministic canonical serialization so `provenance_hash` is stable
    regardless of dict insertion order (sorted keys, no whitespace, no NaN)."""
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )


def build_provenance_manifest(
    *,
    artifact_version_id: str,
    created_by_agent_id: str,
    created_by_agent_version_id: str | None,
    content_hash: str,
    mission_id: str | None,
    mission_task_ids: list[str] | None,
    parent_artifact_version_ids: list[str] | None,
    source_claim_ids: list[str] | None,
    source_evidence_ids: list[str] | None,
    source_artifact_version_ids: list[str] | None,
    declared_inputs: list[str] | None,
    created_at: datetime,
) -> dict[str, Any]:
    return {
        "artifact_version_id": artifact_version_id,
        "created_by_agent_id": created_by_agent_id,
        "created_by_agent_version_id": created_by_agent_version_id,
        "content_hash": content_hash,
        "mission_id": mission_id,
        "mission_task_ids": mission_task_ids or [],
        "parent_artifact_version_ids": parent_artifact_version_ids or [],
        "source_claim_ids": source_claim_ids or [],
        "source_evidence_ids": source_evidence_ids or [],
        "source_artifact_version_ids": source_artifact_version_ids or [],
        "declared_inputs": declared_inputs or [],
        "created_at": created_at.isoformat(),
    }


async def publish_version(
    session: AsyncSession,
    *,
    artifact: Artifact,
    agent_id: str,
    agent_version_id: str | None,
    content_hash: str,
    content_size: int,
    media_type: str,
    display_filename: str | None,
    storage_key: str,
    metadata: dict[str, Any],
    trace_id: str | None,
) -> ArtifactVersion:
    """Server-verified, immutable, monotonic. `content_hash`/`content_size`
    must already be the ArtifactStore's own computed values — never the
    client-declared `client_content_hash`, which is advisory only."""
    mission_id = metadata.get("mission_id")
    mission_task_ids = metadata.get("mission_task_ids") or []

    for task_id in mission_task_ids:
        task = await session.get(MissionTask, task_id)
        if task is None or (mission_id and task.mission_id != mission_id):
            raise NotFound(f"Mission task {task_id} not found for this Mission.")

    for parent_id in metadata.get("parent_artifact_version_ids") or []:
        parent = await session.get(ArtifactVersion, parent_id)
        if parent is None or parent.state != "published":
            raise ValidationFailed(f"Parent artifact version {parent_id} is not published.")

    version_number = artifact.latest_version_number + 1
    version_id = new_artifact_version_id()
    created_at = now_utc()

    manifest = build_provenance_manifest(
        artifact_version_id=version_id,
        created_by_agent_id=agent_id,
        created_by_agent_version_id=agent_version_id,
        content_hash=content_hash,
        mission_id=mission_id,
        mission_task_ids=mission_task_ids,
        parent_artifact_version_ids=metadata.get("parent_artifact_version_ids"),
        source_claim_ids=metadata.get("source_claim_ids"),
        source_evidence_ids=metadata.get("source_evidence_ids"),
        source_artifact_version_ids=metadata.get("source_artifact_version_ids"),
        declared_inputs=metadata.get("declared_inputs"),
        created_at=created_at,
    )
    provenance_hash = hashlib.sha256(canonical_provenance_json(manifest)).hexdigest()

    version = ArtifactVersion(
        artifact_version_id=version_id,
        artifact_id=artifact.artifact_id,
        version_number=version_number,
        state="published",
        created_by_agent_id=agent_id,
        created_by_agent_version_id=agent_version_id,
        content_hash=content_hash,
        content_size=content_size,
        media_type=media_type,
        display_filename=display_filename,
        storage_key=storage_key,
        provenance_manifest=manifest,
        provenance_hash=provenance_hash,
        created_at=created_at,
        published_at=created_at,
    )
    session.add(version)
    artifact.latest_version_number = version_number
    await append_event(
        session,
        event_type="artifact.version_published",
        actor={"agent_id": agent_id, "agent_version_id": agent_version_id},
        payload={
            "artifact_id": artifact.artifact_id,
            "artifact_version_id": version_id,
            "version_number": version_number,
            "content_hash": content_hash,
            "mission_id": mission_id,
            "mission_task_ids": mission_task_ids,
        },
        trace_id=trace_id,
    )
    return version


async def create_review(
    session: AsyncSession,
    *,
    version: ArtifactVersion,
    reviewer_agent_id: str,
    payload: dict[str, Any],
    trace_id: str | None,
) -> ArtifactReview:
    if version.state != "published":
        raise VersionNotPublishable("Cannot review a version that is not published.")

    existing = (
        await session.execute(
            select(ArtifactReview).where(
                ArtifactReview.artifact_version_id == version.artifact_version_id,
                ArtifactReview.reviewer_agent_id == reviewer_agent_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicateReview("This agent already reviewed this exact version.")

    is_self_review = reviewer_agent_id == version.created_by_agent_id
    review = ArtifactReview(
        review_id=new_review_id(),
        artifact_version_id=version.artifact_version_id,
        reviewer_agent_id=reviewer_agent_id,
        verdict=payload["verdict"],
        comment=payload.get("comment"),
        scores=payload.get("scores"),
        is_self_review=is_self_review,
        created_at=now_utc(),
    )
    session.add(review)
    await append_event(
        session,
        event_type="artifact.reviewed",
        actor={"agent_id": reviewer_agent_id},
        payload={
            "artifact_version_id": version.artifact_version_id,
            "review_id": review.review_id,
            "verdict": review.verdict,
            "is_self_review": is_self_review,
        },
        trace_id=trace_id,
    )
    return review


async def independent_review_count(session: AsyncSession, artifact_version_id: str) -> int:
    """Independent = not authored by the version's own creator (self-reviews
    never count toward completion policy thresholds)."""
    reviews = (
        await session.execute(
            select(ArtifactReview).where(
                ArtifactReview.artifact_version_id == artifact_version_id,
                ArtifactReview.is_self_review.is_(False),
                ArtifactReview.verdict == "approve",
            )
        )
    ).scalars().all()
    return len(reviews)
