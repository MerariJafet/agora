"""Event ledger service.

Events are appended in the SAME transaction as the state change they record,
together with an outbox row (ADR-0004). The ledger is append-only: the
application never updates/deletes events and migration 0001 installs DB
triggers rejecting UPDATE/DELETE on `events`.

Heartbeat/presence-style noise must NOT go through this module — it belongs
in Redis ephemeral state, never in the immutable ledger.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.boundary import validate_event_envelope
from agora_api.config import get_settings
from agora_api.ids import new_event_id
from agora_api.models import Event, EventOutbox, RecordProvenance

LEDGER_SUBJECT_PREFIX = "agora.events"


def now_utc() -> datetime:
    return datetime.now(UTC)


async def append_event(
    session: AsyncSession,
    *,
    event_type: str,
    actor: dict[str, Any],
    payload: dict[str, Any],
    schema_version: str = "1.0",
    correlation_id: str | None = None,
    causation_id: str | None = None,
    trace_id: str | None = None,
    provenance_class: str | None = None,
    provenance_environment_id: str | None = None,
    provenance_run_id: str | None = None,
) -> Event:
    """Append an immutable event + outbox row inside the caller's transaction."""
    event = Event(
        event_id=new_event_id(),
        event_type=event_type,
        occurred_at=now_utc(),
        actor=actor,
        payload=payload,
        schema_version=schema_version,
        correlation_id=correlation_id,
        causation_id=causation_id,
        trace_id=trace_id,
    )
    validate_event_envelope(envelope_dict(event))
    session.add(event)
    session.add(
        EventOutbox(
            event_id=event.event_id,
            subject=f"{LEDGER_SUBJECT_PREFIX}.{event_type}",
            published=False,
            created_at=now_utc(),
        )
    )
    settings = get_settings()
    event_provenance_class = provenance_class or (
        "test" if settings.env == "test" else settings.provenance_class
    )
    session.add(
        RecordProvenance(
            record_table="events",
            record_id=event.event_id,
            environment_id=provenance_environment_id or settings.environment_id,
            run_id=provenance_run_id or settings.run_id,
            provenance_class=event_provenance_class,
            created_by_actor_or_process=f"event:{event_type}",
            source_reference=correlation_id or causation_id,
            schema_version="1.0",
            created_at=event.occurred_at,
        )
    )
    return event


def envelope_dict(event: Event) -> dict[str, Any]:
    envelope: dict[str, Any] = {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "occurred_at": event.occurred_at.isoformat().replace("+00:00", "Z"),
        "actor": event.actor,
        "payload": event.payload,
        "schema_version": event.schema_version,
    }
    for key in ("correlation_id", "causation_id", "trace_id", "signature"):
        value = getattr(event, key)
        if value is not None:
            envelope[key] = value
    return envelope
