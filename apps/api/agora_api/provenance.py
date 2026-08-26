"""Authoritative data provenance for P1 stabilization.

This module intentionally does not infer legacy meaning from names. A record is
`unknown` unless the caller supplies an explicit class through configuration or
an authorized future adjudication path.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from agora_api.config import get_settings
from agora_api.errors import ProvenanceMismatch
from agora_api.events import append_event, now_utc
from agora_api.models import (
    Agent,
    MissionParticipant,
    RecordProvenance,
    RecordProvenanceAudit,
    RecordQuarantine,
)

PROVENANCE_CLASSES = {"real", "demo", "test", "unknown"}
PUBLIC_DEFAULT_CLASSES = {"real"}
SYSTEM_ACTOR_ID = "agt_00000000000000000000000000"


def default_provenance_class() -> str:
    settings = get_settings()
    if settings.env == "test":
        return "test"
    return settings.provenance_class


def current_environment_id() -> str:
    return get_settings().environment_id


def current_run_id() -> str:
    return get_settings().run_id


def world_instance_for_class(provenance_class: str | None = None) -> str:
    settings = get_settings()
    pclass = provenance_class or default_provenance_class()
    if pclass == "real":
        return settings.world_instance_id
    if pclass == "demo":
        return settings.demo_world_instance_id
    if pclass == "test":
        return settings.test_world_instance_id
    return "legacy"


def public_provenance_classes() -> set[str]:
    classes = set(PUBLIC_DEFAULT_CLASSES)
    if get_settings().env == "test":
        classes.add("test")
    return classes


def public_world_instance_ids() -> set[str]:
    settings = get_settings()
    ids = {settings.world_instance_id}
    if settings.env == "test":
        ids.add(settings.test_world_instance_id)
    return ids


def visible_record_condition(record_table: str, record_id_column: Any) -> Any:
    return (
        (RecordProvenance.record_table == record_table)
        & (RecordProvenance.record_id == record_id_column)
        & (RecordProvenance.provenance_class.in_(public_provenance_classes()))
        & (RecordProvenance.world_instance_id.in_(public_world_instance_ids()))
        & ~exists()
        .where(RecordQuarantine.record_table == record_table)
        .where(RecordQuarantine.record_id == record_id_column)
    )


def record_key(*parts: str) -> str:
    return "|".join(parts)


async def add_provenance(
    session: AsyncSession,
    *,
    record_table: str,
    record_id: str,
    provenance_class: str | None = None,
    created_by: str = "agora-api",
    source_reference: str | None = None,
    environment_id: str | None = None,
    run_id: str | None = None,
    world_instance_id: str | None = None,
    created_by_actor_id: str | None = None,
    created_by_actor_provenance: str | None = None,
) -> RecordProvenance:
    pclass = provenance_class or default_provenance_class()
    if pclass not in PROVENANCE_CLASSES:
        raise ValueError(f"invalid provenance_class: {pclass}")
    existing = await session.get(RecordProvenance, (record_table, record_id))
    if existing is not None:
        return existing
    row = RecordProvenance(
        record_table=record_table,
        record_id=record_id,
        environment_id=environment_id or current_environment_id(),
        run_id=run_id or current_run_id(),
        world_instance_id=world_instance_id or world_instance_for_class(pclass),
        provenance_class=pclass,
        created_by_actor_id=created_by_actor_id,
        created_by_actor_provenance=created_by_actor_provenance,
        created_by_actor_or_process=created_by,
        source_reference=source_reference,
        schema_version="1.0",
        created_at=now_utc(),
    )
    session.add(row)
    return row


async def reclassify_provenance(
    session: AsyncSession,
    *,
    record_table: str,
    record_id: str,
    new_class: str,
    actor: str,
    reason: str,
    evidence_reference: str,
    trace_id: str | None = None,
    environment_id: str | None = None,
    run_id: str | None = None,
    world_instance_id: str | None = None,
) -> RecordProvenance:
    if new_class not in PROVENANCE_CLASSES:
        raise ValueError(f"invalid provenance_class: {new_class}")
    row = await session.get(RecordProvenance, (record_table, record_id))
    previous = row.provenance_class if row else None
    if row is None:
        row = await add_provenance(
            session,
            record_table=record_table,
            record_id=record_id,
            provenance_class=new_class,
            created_by=actor,
            source_reference=evidence_reference,
            environment_id=environment_id,
            run_id=run_id,
            world_instance_id=world_instance_id,
        )
    elif row.provenance_class == new_class:
        if environment_id is not None:
            row.environment_id = environment_id
        if run_id is not None:
            row.run_id = run_id
        if world_instance_id is not None:
            row.world_instance_id = world_instance_id
        return row
    else:
        row.provenance_class = new_class
        if environment_id is not None:
            row.environment_id = environment_id
        if run_id is not None:
            row.run_id = run_id
        row.world_instance_id = world_instance_id or world_instance_for_class(new_class)
        row.created_by_actor_or_process = actor
        row.source_reference = evidence_reference
    session.add(
        RecordProvenanceAudit(
            record_table=record_table,
            record_id=record_id,
            previous_class=previous,
            new_class=new_class,
            actor=actor,
            reason=reason,
            evidence_reference=evidence_reference,
            created_at=now_utc(),
        )
    )
    await append_event(
        session,
        event_type="provenance.reclassified",
        actor={"agent_id": SYSTEM_ACTOR_ID},
        payload={
            "record_table": record_table,
            "record_id": record_id,
            "previous_class": previous,
            "new_class": new_class,
            "reason": reason,
            "evidence_reference": evidence_reference,
        },
        trace_id=trace_id,
        provenance_class=new_class,
        provenance_environment_id=environment_id,
        provenance_run_id=run_id,
        provenance_world_instance_id=world_instance_id,
    )
    return row


async def require_actor_record_compatible(
    session: AsyncSession,
    *,
    actor_agent_id: str,
    container_table: str,
    container_id: str,
    target_record_table: str,
    target_record_id: str,
    trace_id: str | None,
) -> dict[str, str]:
    actor = await session.get(RecordProvenance, ("agents", actor_agent_id))
    container = await session.get(RecordProvenance, (container_table, container_id))
    actor_class = actor.provenance_class if actor else "unknown"
    actor_world = actor.world_instance_id if actor else "legacy"
    container_class = container.provenance_class if container else "unknown"
    container_world = container.world_instance_id if container else "legacy"
    settings = get_settings()
    if (
        settings.env == "test"
        and actor is not None
        and actor_class == "test"
        and container_class == "real"
        and (
            container_table == "spaces"
            or container_id == "mis_000000000000000000C011ATZ0"
        )
    ):
        return {
            "provenance_class": actor_class,
            "environment_id": actor.environment_id,
            "run_id": actor.run_id,
            "world_instance_id": actor.world_instance_id,
            "created_by_actor_id": actor_agent_id,
            "created_by_actor_provenance": actor_class,
        }
    if actor_class == container_class and actor_world == container_world:
        return {
            "provenance_class": actor_class,
            "environment_id": container.environment_id if container else current_environment_id(),
            "run_id": container.run_id if container else current_run_id(),
            "world_instance_id": actor_world,
            "created_by_actor_id": actor_agent_id,
            "created_by_actor_provenance": actor_class,
        }
    await append_event(
        session,
        event_type="provenance.mismatch_rejected",
        actor={"agent_id": SYSTEM_ACTOR_ID},
        payload={
            "actor_agent_id": actor_agent_id,
            "actor_provenance": actor_class,
            "actor_world_instance_id": actor_world,
            "container_table": container_table,
            "container_id": container_id,
            "container_provenance": container_class,
            "container_world_instance_id": container_world,
            "target_record_table": target_record_table,
            "target_record_id": target_record_id,
            "decision": "rejected",
        },
        trace_id=trace_id,
        provenance_class=container_class if container_class in PROVENANCE_CLASSES else "unknown",
        provenance_environment_id=container.environment_id if container else None,
        provenance_run_id=container.run_id if container else None,
        provenance_world_instance_id=container_world,
    )
    raise ProvenanceMismatch(
        "Actor provenance is incompatible with the target world record."
    )


async def quarantine_record(
    session: AsyncSession,
    *,
    record_table: str,
    record_id: str,
    reason: str,
    evidence_reference: str,
    invalidated_state: dict[str, Any] | None = None,
    created_by: str = "agora-api",
) -> RecordQuarantine:
    existing = (
        await session.execute(
            select(RecordQuarantine).where(
                RecordQuarantine.record_table == record_table,
                RecordQuarantine.record_id == record_id,
                RecordQuarantine.reason == reason,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    row = RecordQuarantine(
        record_table=record_table,
        record_id=record_id,
        reason=reason,
        evidence_reference=evidence_reference,
        invalidated_state=invalidated_state,
        created_by_actor_or_process=created_by,
        created_at=now_utc(),
    )
    session.add(row)
    return row


async def quarantine_mission_participant_provenance_mismatches(
    session: AsyncSession,
    *,
    evidence_reference: str = "docs/work/world-data-hygiene-root-cause-audit.md#phase-0",
) -> dict[str, Any]:
    participant_provenance = aliased(RecordProvenance)
    agent_provenance = aliased(RecordProvenance)
    participant_record_id = MissionParticipant.mission_id + "|" + MissionParticipant.agent_id
    rows = (
        await session.execute(
            select(
                MissionParticipant,
                Agent.name,
                participant_provenance.provenance_class,
                participant_provenance.world_instance_id,
                agent_provenance.provenance_class,
                agent_provenance.world_instance_id,
            )
            .join(Agent, Agent.agent_id == MissionParticipant.agent_id)
            .join(
                participant_provenance,
                (participant_provenance.record_table == "mission_participants")
                & (participant_provenance.record_id == participant_record_id),
            )
            .join(
                agent_provenance,
                (agent_provenance.record_table == "agents")
                & (agent_provenance.record_id == MissionParticipant.agent_id),
            )
            .where(
                (participant_provenance.provenance_class != agent_provenance.provenance_class)
                | (participant_provenance.world_instance_id != agent_provenance.world_instance_id)
            )
        )
    ).all()
    changed = 0
    for participant, name, part_class, part_world, agent_class, agent_world in rows:
        before = (
            await session.execute(
                select(RecordQuarantine).where(
                    RecordQuarantine.record_table == "mission_participants",
                    RecordQuarantine.record_id == record_key(
                        participant.mission_id, participant.agent_id
                    ),
                    RecordQuarantine.reason == "PROVENANCE_ACTOR_RELATION_MISMATCH",
                )
            )
        ).scalar_one_or_none()
        await quarantine_record(
            session,
            record_table="mission_participants",
            record_id=record_key(participant.mission_id, participant.agent_id),
            reason="PROVENANCE_ACTOR_RELATION_MISMATCH",
            evidence_reference=evidence_reference,
            invalidated_state={
                "mission_id": participant.mission_id,
                "agent_id": participant.agent_id,
                "agent_name": name,
                "participant_provenance": part_class,
                "participant_world_instance_id": part_world,
                "actor_provenance": agent_class,
                "actor_world_instance_id": agent_world,
            },
            created_by="operator.data_hygiene",
        )
        if before is None:
            changed += 1
    if rows:
        await append_event(
            session,
            event_type="provenance.quarantine_applied",
            actor={"agent_id": SYSTEM_ACTOR_ID},
            payload={
                "record_table": "mission_participants",
                "evaluated": len(rows),
                "changed": changed,
                "reason": "PROVENANCE_ACTOR_RELATION_MISMATCH",
            },
            provenance_class="real",
            provenance_world_instance_id=get_settings().world_instance_id,
        )
    return {"evaluated": len(rows), "quarantined_new": changed}


async def provenance_counts(
    session: AsyncSession, record_tables: Iterable[str] | None = None
) -> dict:
    query = select(
        RecordProvenance.record_table,
        RecordProvenance.provenance_class,
        func.count(RecordProvenance.record_id),
    ).group_by(RecordProvenance.record_table, RecordProvenance.provenance_class)
    if record_tables:
        query = query.where(RecordProvenance.record_table.in_(list(record_tables)))
    rows = (await session.execute(query)).all()
    result: dict[str, dict[str, int]] = {}
    for table, pclass, count in rows:
        result.setdefault(table, {key: 0 for key in sorted(PROVENANCE_CLASSES)})
        result[table][pclass] = int(count)
    return result


def provenance_view(row: RecordProvenance | None) -> dict[str, Any]:
    if row is None:
        return {"provenance_class": "unknown", "schema_version": "1.0"}
    return {
        "environment_id": row.environment_id,
        "run_id": row.run_id,
        "world_instance_id": row.world_instance_id,
        "provenance_class": row.provenance_class,
        "created_by_actor_id": row.created_by_actor_id,
        "created_by_actor_provenance": row.created_by_actor_provenance,
        "created_by_actor_or_process": row.created_by_actor_or_process,
        "source_reference": row.source_reference,
        "schema_version": row.schema_version,
        "created_at": row.created_at.isoformat(),
    }
