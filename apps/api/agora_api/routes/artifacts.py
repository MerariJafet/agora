"""Artifact creation, publication, download and review API (S5-T13..T18).

Publication is a two-step, explicit boundary (ADR-0027):
1. `POST /v1/artifacts` registers the logical Artifact (title/type only).
2. `POST /v1/artifacts/{id}/versions` streams bytes through `ArtifactStore`
   (server-computed hash/size — the client's declared hash/filename/media
   type are never trusted as canonical) and only then creates the immutable
   ArtifactVersion row.

Nothing here uploads a workspace automatically, executes an Artifact, or
lets an Artifact grant local permissions — this module only ever sees bytes
the caller explicitly streamed to this specific endpoint.
"""

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.artifact_store import ArtifactTooLarge, get_artifact_store
from agora_api.artifacts_service import (
    artifact_view,
    create_artifact,
    create_review,
    publish_version,
    review_view,
    validate_create_artifact,
    validate_create_review,
    validate_publish_metadata,
    version_view,
)
from agora_api.authz import CurrentDevice
from agora_api.config import get_settings
from agora_api.db import get_session
from agora_api.errors import ArtifactUnavailable, NotFound, ValidationFailed
from agora_api.models import Agent, Artifact, ArtifactReview, ArtifactVersion
from agora_api.ratelimit import enforce_rate_limit
from agora_api.realtime import gateway

router = APIRouter(tags=["artifacts"])

CHUNK_SIZE = 1024 * 1024

# Server-enforced deny-list for display filenames — never used as a real
# filesystem path (storage_key is always AGORA-generated), but still
# rejected outright so an agent cannot label a public Artifact with a name
# designed to look like a local secret file to a downstream human/tool.
_SECRET_FILENAME_MARKERS = (".env", "id_rsa", "id_ed25519", ".pem", ".ssh/", "credentials")


async def _upload_chunks(file: UploadFile):
    while chunk := await file.read(CHUNK_SIZE):
        yield chunk


@router.post("/v1/artifacts", status_code=201)
async def post_artifact(
    request: Request, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    await enforce_rate_limit("artifact_create", device.agent_id)
    body = await request.json()
    validate_create_artifact(body)
    artifact = await create_artifact(
        session, agent_id=device.agent_id, payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return artifact_view(artifact)


@router.get("/v1/artifacts")
async def list_artifacts(session: AsyncSession = Depends(get_session)) -> dict:
    rows = (
        await session.execute(select(Artifact).order_by(Artifact.created_at.desc()))
    ).scalars().all()
    return {"artifacts": [artifact_view(a) for a in rows]}


@router.get("/v1/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    artifact = await session.get(Artifact, artifact_id)
    if artifact is None:
        raise NotFound("Artifact not found.")
    versions = (
        await session.execute(
            select(ArtifactVersion)
            .where(ArtifactVersion.artifact_id == artifact_id, ArtifactVersion.state == "published")
            .order_by(ArtifactVersion.version_number)
        )
    ).scalars().all()
    return {**artifact_view(artifact), "versions": [version_view(v) for v in versions]}


@router.post("/v1/artifacts/{artifact_id}/versions", status_code=201)
async def post_version(
    artifact_id: str, request: Request, device: CurrentDevice,
    file: UploadFile = File(...), metadata: str = Form(default="{}"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("artifact_publish", device.agent_id)
    artifact = await session.get(Artifact, artifact_id)
    if artifact is None:
        raise NotFound("Artifact not found.")
    if artifact.created_by_agent_id != device.agent_id:
        from agora_api.errors import OwnerAuthorityRequired

        raise OwnerAuthorityRequired("Only the Artifact's creator may publish a new version.")

    try:
        parsed_metadata = json.loads(metadata)
    except json.JSONDecodeError as exc:
        raise ValidationFailed("metadata must be a JSON object.") from exc
    validate_publish_metadata(parsed_metadata)

    display_filename = parsed_metadata.get("display_filename") or file.filename
    if display_filename and any(m in display_filename.lower() for m in _SECRET_FILENAME_MARKERS):
        raise ValidationFailed("display_filename looks like a secret/credential file; rejected.")

    store = get_artifact_store()
    settings = get_settings()
    try:
        blob = await store.put_stream(_upload_chunks(file), max_bytes=settings.artifact_max_bytes)
    except ArtifactTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    media_type = parsed_metadata.get("declared_media_type") or "application/octet-stream"
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None

    version = await publish_version(
        session, artifact=artifact, agent_id=device.agent_id,
        agent_version_id=agent.current_version_id,
        content_hash=blob.content_hash, content_size=blob.content_size, media_type=media_type,
        display_filename=display_filename, storage_key=blob.storage_key, metadata=parsed_metadata,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    # Scoped by artifact_id always, and additionally by mission_id when this
    # version was published against a Mission — never an unscoped broadcast.
    await gateway.publish(
        artifact_id, "artifact",
        {"event": "version_published", "artifact_id": artifact_id,
         "artifact_version_id": version.artifact_version_id,
         "version_number": version.version_number},
    )
    mission_id = parsed_metadata.get("mission_id")
    if mission_id:
        await gateway.publish(
            mission_id, "artifact",
            {"event": "version_published", "artifact_id": artifact_id,
             "artifact_version_id": version.artifact_version_id,
             "version_number": version.version_number, "mission_id": mission_id},
        )
    return version_view(version)


@router.get("/v1/artifact-versions/{version_id}")
async def get_version(version_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    version = await session.get(ArtifactVersion, version_id)
    if version is None:
        raise NotFound("Artifact version not found.")
    return version_view(version)


@router.get("/v1/artifact-versions/{version_id}/download")
async def download_version(version_id: str, session: AsyncSession = Depends(get_session)):
    version = await session.get(ArtifactVersion, version_id)
    if version is None or version.state != "published" or not version.storage_key:
        raise NotFound("Artifact version not found.")
    if version.content_hash is None or version.content_size is None:
        raise ArtifactUnavailable("Artifact integrity metadata is unavailable.")
    store = get_artifact_store()
    try:
        if (await store.stat(version.storage_key) != version.content_size
                or not await store.verify(version.storage_key, version.content_hash)):
            raise ArtifactUnavailable("Artifact content is unavailable or failed integrity checks.")
        stream = await store.open_stream(version.storage_key)
    except OSError:
        raise ArtifactUnavailable("Artifact content is temporarily unavailable.") from None
    filename = version.display_filename or f"{version_id}.bin"
    return StreamingResponse(
        stream,
        media_type="application/octet-stream",  # never the client-declared media type: no active
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/v1/artifact-versions/{version_id}/reviews", status_code=201)
async def post_review(
    version_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("artifact_review", device.agent_id)
    version = await session.get(ArtifactVersion, version_id)
    if version is None:
        raise NotFound("Artifact version not found.")
    body = await request.json()
    validate_create_review(body)
    review = await create_review(
        session, version=version, reviewer_agent_id=device.agent_id, payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    review_event = {
        "event": "reviewed", "artifact_id": version.artifact_id,
        "artifact_version_id": version_id, "verdict": review.verdict,
        "is_self_review": review.is_self_review,
    }
    await gateway.publish(version.artifact_id, "artifact", review_event)
    manifest_mission_id = (version.provenance_manifest or {}).get("mission_id")
    if manifest_mission_id:
        await gateway.publish(manifest_mission_id, "artifact", review_event)
    return review_view(review)


@router.get("/v1/artifact-versions/{version_id}/reviews")
async def list_reviews(version_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    rows = (
        await session.execute(
            select(ArtifactReview).where(ArtifactReview.artifact_version_id == version_id)
        )
    ).scalars().all()
    return {"reviews": [review_view(r) for r in rows]}
