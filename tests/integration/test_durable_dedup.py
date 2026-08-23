"""Durable consumer idempotency (S2-T01): dedup survives process restart."""

import secrets

import pytest
from sqlalchemy import func, select

from agora_api.consumers import DurableConsumer
from agora_api.db import session_factory
from agora_api.models import ProcessedEvent

pytestmark = pytest.mark.integration


def _envelope(event_id: str) -> dict:
    return {
        "event_id": event_id,
        "event_type": "agent.registered",
        "occurred_at": "2026-08-22T00:00:00Z",
        "actor": {"agent_id": "agt_" + "3" * 26},
        "payload": {},
        "schema_version": "1.0",
    }


async def test_duplicate_delivery_survives_restart():
    """Same consumer name, NEW instance (simulated process restart after the
    broker failed to receive an ack): the redelivered event must be skipped
    because the mark is persistent, not in memory."""
    consumer_name = f"test-durable-{secrets.token_hex(4)}"
    applied: list[str] = []

    async def apply(session, envelope):
        applied.append(envelope["event_id"])

    event_id = f"evt_{secrets.token_hex(13).upper()[:26]}"
    first_process = DurableConsumer(consumer_name, session_factory(), apply)
    assert await first_process.handle(_envelope(event_id)) is True

    # --- process restart: brand-new instance, zero in-memory state ---
    second_process = DurableConsumer(consumer_name, session_factory(), apply)
    assert await second_process.handle(_envelope(event_id)) is False
    assert second_process.duplicates_skipped == 1
    assert applied == [event_id]

    async with session_factory()() as session:
        count = (
            await session.execute(
                select(func.count()).where(
                    ProcessedEvent.consumer_name == consumer_name,
                    ProcessedEvent.event_id == event_id,
                )
            )
        ).scalar_one()
        assert count == 1


async def test_crash_before_commit_allows_safe_retry():
    """If apply() raises (crash mid-processing), the mark rolls back with it:
    the event is NOT recorded as processed and redelivery reprocesses it."""
    consumer_name = f"test-crash-{secrets.token_hex(4)}"
    attempts: list[int] = []

    async def flaky_apply(session, envelope):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("simulated crash before commit")

    event_id = f"evt_{secrets.token_hex(13).upper()[:26]}"
    consumer = DurableConsumer(consumer_name, session_factory(), flaky_apply)
    with pytest.raises(RuntimeError):
        await consumer.handle(_envelope(event_id))

    # redelivery after the crash: must actually process (not falsely deduped)
    retry_consumer = DurableConsumer(consumer_name, session_factory(), flaky_apply)
    assert await retry_consumer.handle(_envelope(event_id)) is True
    assert len(attempts) == 2


async def test_distinct_consumers_process_independently():
    async def apply(session, envelope):
        pass

    event_id = f"evt_{secrets.token_hex(13).upper()[:26]}"
    a = DurableConsumer(f"cons-a-{secrets.token_hex(3)}", session_factory(), apply)
    b = DurableConsumer(f"cons-b-{secrets.token_hex(3)}", session_factory(), apply)
    assert await a.handle(_envelope(event_id)) is True
    assert await b.handle(_envelope(event_id)) is True  # different consumer identity