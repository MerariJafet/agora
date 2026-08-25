"""Authoritative data provenance for P1 stabilization.

This module intentionally does not infer legacy meaning from names. A record is
`unknown` unless the caller supplies an explicit class through configuration or
an authorized future adjudication path.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.config import get_settings
from agora_api.events import append_event, now_utc
from agora_api.models import RecordProvenance, RecordProvenanceAudit

PROVENANCE_CLASSES = {"real", "demo", "test", "unknown"}
PUBLIC_DEFAULT_CLASSES = {"real", "demo", "unknown"}


def default_provenance_class() -> str:
    settings = get_settings()
    if settings.env == "test":
        return "test"
    return settings.provenance_class


def current_environment_id() -> str:
    return get_settings().environment_id


def current_run_id() -> str:
    return get_settings().run_id


def public_provenance_classes() -> set[str]:
    classes = set(PUBLIC_DEFAULT_CLASSES)
    if get_settings().env == "test":
        classes.add("test")
    return classes


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
        provenance_class=pclass,
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
        )
    elif row.provenance_class == new_class:
        return row
    else:
        row.provenance_class = new_class
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
        actor={"process": actor},
        payload={
            "record_table": record_table,
            "record_id": record_id,
            "previous_class": previous,
            "new_class": new_class,
            "reason": reason,
            "evidence_reference": evidence_reference,
        },
        trace_id=trace_id,
    )
    return row


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
        "provenance_class": row.provenance_class,
        "created_by_actor_or_process": row.created_by_actor_or_process,
        "source_reference": row.source_reference,
        "schema_version": row.schema_version,
        "created_at": row.created_at.isoformat(),
    }
