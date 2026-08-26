"""Owner-authorized provenance adjudication for the current local experiment."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.events import append_event
from agora_api.models import Agent, Device, Mission, MissionParticipant, RecordProvenance, Space
from agora_api.provenance import SYSTEM_ACTOR_ID, reclassify_provenance, record_key

DEFAULT_AUTHORIZED_AGENT_NAMES = [
    "Agora-Ollama",
    "Agora-Codex",
    "Agora-Antigravity",
    "Agora-Ollama-Scout",
    "Agora-Codex-Archivist",
    "Agora-Antigravity-Mediator",
    "Agora-Alpha",
]

OWNER_AUTHORIZATION_REFERENCE = "AGORA_P1_CLOSURE_AND_CONTROLLED_VALIDATION.json#phase_3"


class ProvenanceAdjudicationError(RuntimeError):
    pass


def canonical_manifest_hash(manifest: dict[str, Any]) -> str:
    unsigned = {k: v for k, v in manifest.items() if k != "manifest_hash"}
    raw = json.dumps(
        unsigned,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    ).encode()
    return hashlib.sha256(raw).hexdigest()


async def _provenance_class(session: AsyncSession, table: str, record_id: str) -> str:
    row = await session.get(RecordProvenance, (table, record_id))
    return row.provenance_class if row else "unknown"


async def build_adjudication_manifest(
    session: AsyncSession,
    *,
    authorized_agent_names: Sequence[str] = DEFAULT_AUTHORIZED_AGENT_NAMES,
    configured_agent_ids: dict[str, str] | None = None,
    mission_id: str,
    space_id: str,
    target_class: str = "real",
) -> dict[str, Any]:
    if len(set(authorized_agent_names)) != len(authorized_agent_names):
        raise ProvenanceAdjudicationError("authorized agent names contain duplicates")
    rows = (
        await session.execute(select(Agent).where(Agent.name.in_(list(authorized_agent_names))))
    ).scalars().all()
    agents_by_name = {row.name: row for row in rows}
    missing = sorted(set(authorized_agent_names) - set(agents_by_name))
    if missing:
        raise ProvenanceAdjudicationError(f"authorized agents missing: {missing}")
    if len(rows) != len(authorized_agent_names):
        raise ProvenanceAdjudicationError("authorized agent lookup was not exact")
    configured_agent_ids = configured_agent_ids or {}
    mismatches = {
        name: {"configured": configured_agent_ids[name], "database": agents_by_name[name].agent_id}
        for name in configured_agent_ids
        if name in agents_by_name and configured_agent_ids[name] != agents_by_name[name].agent_id
    }
    if mismatches:
        raise ProvenanceAdjudicationError(f"configured agent IDs mismatch: {mismatches}")

    mission = await session.get(Mission, mission_id)
    if mission is None or not mission.challenge_kind:
        raise ProvenanceAdjudicationError(f"mission is not an active challenge: {mission_id}")
    if mission.hosting_space_id != space_id:
        raise ProvenanceAdjudicationError(
            "mission hosting_space_id does not match authorized space"
        )
    space = await session.get(Space, space_id)
    if space is None:
        raise ProvenanceAdjudicationError(f"authorized space not found: {space_id}")

    agent_ids = [agents_by_name[name].agent_id for name in authorized_agent_names]
    records: list[dict[str, Any]] = []

    async def add_record(table: str, rid: str, reason: str) -> None:
        records.append(
            {
                "record_table": table,
                "record_id": rid,
                "previous_class": await _provenance_class(session, table, rid),
                "proposed_class": target_class,
                "reason": reason,
                "owner_authorization_reference": OWNER_AUTHORIZATION_REFERENCE,
            }
        )

    for name in authorized_agent_names:
        await add_record("agents", agents_by_name[name].agent_id, f"authorized exact agent {name}")
    devices = (
        await session.execute(select(Device).where(Device.agent_id.in_(agent_ids)))
    ).scalars().all()
    for device in sorted(devices, key=lambda row: row.device_id):
        await add_record("devices", device.device_id, f"authorized device for {device.agent_id}")
    await add_record("missions", mission_id, "authorized active Collatz challenge")
    await add_record("spaces", space_id, "authorized active Collatz challenge space")
    participants = (
        await session.execute(
            select(MissionParticipant).where(
                MissionParticipant.mission_id == mission_id,
                MissionParticipant.agent_id.in_(agent_ids),
            )
        )
    ).scalars().all()
    for participant in sorted(participants, key=lambda row: row.agent_id):
        await add_record(
            "mission_participants",
            record_key(participant.mission_id, participant.agent_id),
            f"authorized participant for {participant.agent_id}",
        )

    manifest = {
        "schema_version": "1.0",
        "deterministic": True,
        "authorized_agent_names": list(authorized_agent_names),
        "agent_ids": agent_ids,
        "mission_id": mission_id,
        "space_id": space_id,
        "target_class": target_class,
        "records": records,
        "limitations": [
            "No name-matched historical records are included.",
            (
                "Only exact configured/database Agent IDs and current challenge "
                "relationships are selected."
            ),
            "Semantic content, timestamps, ownership and balances are unchanged.",
        ],
    }
    manifest["manifest_hash"] = canonical_manifest_hash(manifest)
    return manifest


async def apply_adjudication_manifest(
    session: AsyncSession,
    manifest: dict[str, Any],
    *,
    actor: str = "owner_authorized_p1_closure",
) -> dict[str, Any]:
    expected = canonical_manifest_hash(manifest)
    if manifest.get("manifest_hash") != expected:
        raise ProvenanceAdjudicationError("adjudication manifest hash mismatch")
    changed = 0
    for record in manifest["records"]:
        before = await _provenance_class(session, record["record_table"], record["record_id"])
        row = await reclassify_provenance(
            session,
            record_table=record["record_table"],
            record_id=record["record_id"],
            new_class=record["proposed_class"],
            actor=actor,
            reason=record["reason"],
            evidence_reference=manifest["manifest_hash"],
        )
        if before != row.provenance_class:
            changed += 1
    await append_event(
        session,
        event_type="provenance.adjudication_manifest_applied",
        actor={"agent_id": SYSTEM_ACTOR_ID},
        payload={
            "manifest_hash": manifest["manifest_hash"],
            "record_count": len(manifest["records"]),
            "changed_count": changed,
            "mission_id": manifest["mission_id"],
            "space_id": manifest["space_id"],
            "agent_ids": manifest["agent_ids"],
        },
    )
    return {"changed": changed, "record_count": len(manifest["records"])}
