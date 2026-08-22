"""Outbox redelivery semantics (S1.1-T04): at-least-once, stable event_id,
no duplicate ledger records, idempotent consumers."""

import json

import pytest
from agora_api.consumers import IdempotentConsumer
from agora_api.db import session_factory
from agora_api.events import append_event
from agora_api.models import Event, EventOutbox
from agora_api.publisher import OutboxDrainer
from sqlalchemy import func, select

pytestmark = pytest.mark.integration


class RecordingPublisher:
    """Test double for the EventPublisher boundary. Can fail on demand to
    simulate 'published to NATS but crashed before mark-delivered' and plain
    broker outages."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []  # (subject, msg_id)
        self.fail_once_for: str | None = None  # msg_id to fail on next attempt

    async def publish(self, subject: str, body: bytes, msg_id: str) -> None:
        if self.fail_once_for == msg_id:
            self.fail_once_for = None
            raise RuntimeError("simulated broker failure")
        json.loads(body)  # envelope must always be valid JSON
        self.published.append((subject, msg_id))


async def _append_test_event(agent_suffix: str) -> str:
    from agora_api.ids import new_agent_id

    async with session_factory()() as session:
        event = await append_event(
            session,
            event_type="agent.registered",
            actor={"agent_id": new_agent_id()},
            payload={"test": f"outbox-{agent_suffix}"},
        )
        await session.commit()
        return event.event_id


async def test_retry_after_failure_republishes_same_event_id():
    event_id = await _append_test_event("11")
    publisher = RecordingPublisher()
    drainer = OutboxDrainer(publisher)  # type: ignore[arg-type]

    publisher.fail_once_for = event_id
    await drainer.drain_once()  # attempt 1 fails for our event; row stays pending
    async with session_factory()() as session:
        row = (
            await session.execute(
                select(EventOutbox).where(EventOutbox.event_id == event_id)
            )
        ).scalar_one()
        assert row.published is False and row.attempts >= 1

    await drainer.drain_once()  # retry succeeds
    ids = [msg_id for _, msg_id in publisher.published]
    assert event_id in ids

    async with session_factory()() as session:
        # exactly one logical ledger record, marked published exactly once
        events = (
            await session.execute(
                select(func.count()).where(Event.event_id == event_id)
            )
        ).scalar_one()
        assert events == 1
        row = (
            await session.execute(
                select(EventOutbox).where(EventOutbox.event_id == event_id)
            )
        ).scalar_one()
        assert row.published is True


async def test_duplicate_delivery_does_not_duplicate_consumer_result():
    """At-least-once delivery: the same envelope arriving twice must produce
    exactly one materialized effect."""
    materialized: list[str] = []
    consumer = IdempotentConsumer(
        "test-projector", lambda env: materialized.append(env["event_id"])
    )

    envelope = {
        "event_id": "evt_" + "7" * 26,
        "event_type": "agent.registered",
        "occurred_at": "2026-08-22T00:00:00Z",
        "actor": {"agent_id": "agt_" + "7" * 26},
        "payload": {},
        "schema_version": "1.0",
    }
    assert consumer.handle(envelope) is True
    assert consumer.handle(envelope) is False  # duplicate delivery
    assert consumer.handle(dict(envelope)) is False  # even as a distinct object
    assert materialized == [envelope["event_id"]]
    assert consumer.duplicates_skipped == 2


async def test_outbox_stats_report_pending_backlog():
    from agora_api.publisher import outbox_stats

    event_id = await _append_test_event("22")
    async with session_factory()() as session:
        stats = await outbox_stats(session)
    assert stats["pending"] >= 1
    assert stats["oldest_pending_seconds"] >= 0
    assert set(stats) == {"pending", "max_attempts", "oldest_pending_seconds"}

    # drain so later tests/suites start from an empty backlog
    publisher = RecordingPublisher()
    drainer = OutboxDrainer(publisher)  # type: ignore[arg-type]
    while await drainer.drain_once():
        pass
    assert event_id in [m for _, m in publisher.published]