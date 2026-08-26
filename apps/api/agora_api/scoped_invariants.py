"""Scoped critical-invariant snapshots for a living AGORA world.

A whole-database hash is invalid while agents are alive: ordinary social
events, movement and presence change legitimately. This module hashes only the
critical invariants that must not drift without an attributable formal event.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.mission_challenges_service import COLLATZ_MISSION_ID
from agora_api.models import (
    AgentGenesis,
    EventOutbox,
    Mission,
    MissionChallengeSubmission,
    MissionChallengeVote,
    TokoinLedgerEntry,
    TokoinWallet,
)
from agora_api.tokoins_service import MAX_SUPPLY_ACEROS, tokoin_status, verify_ledger_chain
from agora_api.world import build_manifest
from agora_api.world_signing import sign_manifest


def canonical_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    ).encode()
    return hashlib.sha256(raw).hexdigest()


async def migration_version(session: AsyncSession) -> str | None:
    try:
        return (
            await session.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
        ).scalar_one_or_none()
    except Exception:  # noqa: BLE001 - snapshots may be used before alembic exists in unit tests
        return None


async def capture_critical_invariants(session: AsyncSession) -> dict[str, Any]:
    manifest = sign_manifest(build_manifest())
    mission = await session.get(Mission, COLLATZ_MISSION_ID)
    reward_entries = int(
        (
            await session.execute(
                select(func.count(TokoinLedgerEntry.entry_id)).where(
                    TokoinLedgerEntry.mission_id == COLLATZ_MISSION_ID,
                    TokoinLedgerEntry.entry_type == "mission_reward",
                )
            )
        ).scalar_one()
    )
    submissions = int(
        (
            await session.execute(
                select(func.count(MissionChallengeSubmission.submission_id)).where(
                    MissionChallengeSubmission.mission_id == COLLATZ_MISSION_ID
                )
            )
        ).scalar_one()
    )
    votes = int(
        (
            await session.execute(
                select(func.count(MissionChallengeVote.submission_id))
                .join(MissionChallengeSubmission)
                .where(MissionChallengeSubmission.mission_id == COLLATZ_MISSION_ID)
            )
        ).scalar_one()
    )
    wallet_total = int(
        (
            await session.execute(select(func.coalesce(func.sum(TokoinWallet.balance), 0)))
        ).scalar_one()
    )
    genesis_duplicates = int(
        (
            await session.execute(
                select(func.count()).select_from(
                    select(AgentGenesis.agent_id)
                    .group_by(AgentGenesis.agent_id)
                    .having(func.count(AgentGenesis.genesis_event_id) > 1)
                    .subquery()
                )
            )
        ).scalar_one()
    )
    outbox_failed = int(
        (
            await session.execute(
                select(func.count(EventOutbox.outbox_id)).where(EventOutbox.attempts >= 10)
            )
        ).scalar_one()
    )
    tokoin = await tokoin_status(session)
    chain = await verify_ledger_chain(session)
    challenge = {
        "exists": mission is not None,
        "state": mission.state if mission else None,
        "deadline_at": mission.deadline_at.isoformat() if mission and mission.deadline_at else None,
        "reward_aceros": mission.reward_aceros if mission else None,
        "resolution_policy": mission.resolution_policy if mission else None,
        "winning_submission_id": mission.winning_submission_id if mission else None,
        "resolved_at": mission.resolved_at.isoformat() if mission and mission.resolved_at else None,
        "submissions": submissions,
        "votes": votes,
        "reward_entries": reward_entries,
    }
    invariants = {
        "schema_version": "1.0",
        "tokoin": {
            "max_supply_aceros": tokoin["max_supply_aceros"],
            "wallet_total_aceros": wallet_total,
            "supply_reconciles": wallet_total == MAX_SUPPLY_ACEROS,
            "chain_valid": bool(chain["valid"]),
            "ledger_entries": chain.get("entries"),
            "ledger_last_hash": chain.get("tip_hash"),
        },
        "collatz": challenge,
        "manifest": {
            "constitution_hash": manifest["constitution_hash"],
            "epoch": manifest["epoch"],
            "key_id": manifest["signature"]["key_id"],
            "payload_hash": manifest["signature"]["payload_hash"],
        },
        "lineage": {"genesis_uniqueness_violations": genesis_duplicates},
        "outbox": {"failed_count": outbox_failed},
    }
    return invariants


async def activity_delta(session: AsyncSession, before_event_count: int) -> dict[str, Any]:
    current_events = int((await session.execute(text("SELECT count(*) FROM events"))).scalar_one())
    return {
        "event_count_before": before_event_count,
        "event_count_after": current_events,
        "events_added": current_events - before_event_count,
    }


async def capture_snapshot_manifest(
    session: AsyncSession,
    *,
    provenance_scope: str = "critical",
    before_event_count: int | None = None,
) -> dict[str, Any]:
    invariants = await capture_critical_invariants(session)
    snapshot = {
        "captured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "world_epoch": invariants["manifest"]["epoch"],
        "database_migration_version": await migration_version(session),
        "provenance_scope": provenance_scope,
        "query_versions": {
            "critical_invariants": "1.0",
            "tokoin_chain": "1.0",
            "collatz_policy": "1.0",
        },
        "canonical_serialization_version": "json-sort-compact-v1",
        "critical_invariants": invariants,
    }
    snapshot["critical_hash"] = canonical_hash(invariants)
    if before_event_count is not None:
        snapshot["activity_delta"] = await activity_delta(session, before_event_count)
    return snapshot
