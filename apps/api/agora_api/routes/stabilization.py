"""P1 stabilization read-only operator status."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.db import get_session
from agora_api.mission_challenges_service import COLLATZ_MISSION_ID, get_challenge_detail
from agora_api.models import EventOutbox, Mission, MissionChallengeSubmission, TokoinLedgerEntry
from agora_api.provenance import provenance_counts
from agora_api.tokoins_service import tokoin_status, verify_ledger_chain
from agora_api.world import build_manifest
from agora_api.world_signing import sign_manifest, trust_bootstrap, verify_manifest

router = APIRouter(prefix="/v1/operator", tags=["operator"])


def _provider_degradation() -> dict:
    base = Path("/home/merari-acero/.agora-agents")
    result: dict[str, int] = {}
    if not base.exists():
        return result
    for memory in base.glob("*/memory.md"):
        try:
            count = memory.read_text(errors="ignore").count("runtime_unavailable")
        except OSError:
            continue
        if count:
            result[memory.parent.name] = count
    return result


@router.get("/stabilization-status")
async def stabilization_status(session: AsyncSession = Depends(get_session)) -> dict:
    manifest = sign_manifest(build_manifest())
    trust = trust_bootstrap()
    signature_ok = verify_manifest(
        manifest,
        trusted_public_keys={key["key_id"]: key["public_key"] for key in trust["active_keys"]},
        min_epoch=trust["minimum_epoch"],
        expected_constitution_hash=trust["constitution_hash"],
    )
    pending_outbox = (
        await session.execute(
            select(func.count(EventOutbox.outbox_id)).where(EventOutbox.published.is_(False))
        )
    ).scalar_one()
    challenge = await get_challenge_detail(session, COLLATZ_MISSION_ID)
    reward_count = (
        await session.execute(
            select(func.count(TokoinLedgerEntry.entry_id)).where(
                TokoinLedgerEntry.mission_id == COLLATZ_MISSION_ID,
                TokoinLedgerEntry.entry_type == "mission_reward",
            )
        )
    ).scalar_one()
    challenge_rows = (
        await session.execute(
            select(func.count(Mission.mission_id)).where(Mission.challenge_kind.is_not(None))
        )
    ).scalar_one()
    submissions = (
        await session.execute(
            select(func.count(MissionChallengeSubmission.submission_id)).where(
                MissionChallengeSubmission.mission_id == COLLATZ_MISSION_ID
            )
        )
    ).scalar_one()
    return {
        "status": "ok",
        "provenance_counts": await provenance_counts(session),
        "manifest_signature": {
            "verified": signature_ok,
            "key_id": manifest["signature"]["key_id"],
            "algorithm": manifest["signature"]["algorithm"],
            "constitution_hash": manifest["constitution_hash"],
            "epoch": manifest["epoch"],
        },
        "challenge_formal_state": {
            "total_challenge_missions": int(challenge_rows),
            "collatz": challenge,
            "collatz_submission_count": int(submissions),
            "collatz_reward_entries": int(reward_count),
        },
        "tokoin": {
            "status": await tokoin_status(session),
            "ledger_chain": await verify_ledger_chain(session),
        },
        "outbox": {"pending": int(pending_outbox)},
        "provider_degradation": _provider_degradation(),
        "scope": "implemented|isolated-tested|live-experimental-local; not production-ready",
    }
