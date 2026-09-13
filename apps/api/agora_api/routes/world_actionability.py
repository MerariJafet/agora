"""P2 world actionability, identity metadata and Unknown Signal APIs."""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.config import get_settings
from agora_api.db import get_session
from agora_api.unknown_signal_readiness import (
    apply_unknown_signal_adjudication_manifest,
    build_unknown_signal_adjudication_manifest,
)
from agora_api.world_actionability import (
    UNKNOWN_SIGNAL_MISSION_ID,
    challenge_actionability,
    ensure_unknown_signal_experiment,
    get_public_unknown_signal_dataset,
    list_agent_identity_metadata,
    observatory_summary,
    unknown_signal_csv,
)
from agora_api.world_digest import world_digest

router = APIRouter(tags=["world-actionability"])


@router.get("/v1/world/agents/identity-metadata")
async def get_agent_identity_metadata(session: AsyncSession = Depends(get_session)) -> dict:
    identities = await list_agent_identity_metadata(session)
    await session.commit()
    return {"agents": identities}


@router.get("/v1/mission-challenges/{mission_id}/actionability")
async def get_challenge_actionability(
    mission_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    return await challenge_actionability(session, mission_id)


@router.get("/v1/observatory/actionability")
async def get_observatory_actionability(
    window_seconds: int = Query(default=3600, ge=60, le=86400),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await observatory_summary(session, window_seconds=window_seconds)


@router.get("/v1/world/digest")
async def get_world_digest(
    window_seconds: int = Query(default=1800, ge=60, le=21600),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Human-language deterministic digest of the last window of world activity."""
    return await world_digest(session, window_seconds=window_seconds)


@router.post("/v1/operator/unknown-signal/round-1/register", status_code=201)
async def register_unknown_signal_round_1(session: AsyncSession = Depends(get_session)) -> dict:
    experiment = await ensure_unknown_signal_experiment(session)
    adjudication = None
    if get_settings().env != "test":
        manifest = await build_unknown_signal_adjudication_manifest(session)
        adjudication = await apply_unknown_signal_adjudication_manifest(session, manifest)
    await session.commit()
    return {
        "experiment_id": experiment.experiment_id,
        "run_id": experiment.run_id,
        "status": experiment.status,
        "cohort_manifest_hash": experiment.cohort_manifest_hash,
        "protocol_manifest_hash": experiment.protocol_manifest_hash,
        "dataset_manifest_hash": experiment.dataset_manifest_hash,
        "sealed_ground_truth_hash": experiment.sealed_ground_truth_hash,
        "public_instruction_hash": experiment.public_instruction_hash,
        "zero_formal_action_is_valid": True,
        "challenge_mission_id": UNKNOWN_SIGNAL_MISSION_ID,
        "provenance_adjudication": adjudication,
    }


@router.get("/v1/unknown-signal/round-1/dataset")
async def get_unknown_signal_dataset(session: AsyncSession = Depends(get_session)) -> dict:
    return await get_public_unknown_signal_dataset(session)


@router.get("/v1/unknown-signal/round-1/dataset.csv", response_class=PlainTextResponse)
async def get_unknown_signal_dataset_csv(
    limit: int = Query(default=5000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
) -> str:
    return unknown_signal_csv(limit=limit, offset=offset)
