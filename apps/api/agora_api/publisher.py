"""Event Publisher boundary + outbox drainer.

Strategy (documented for S1-T10):
- Ordering: outbox rows drain in `outbox_id` (insertion) order; JetStream
  preserves publish order per subject prefix. Global total order is NOT
  guaranteed across event types — consumers needing order use `event_id`
  (ULID, time-sortable) or `causation_id`.
- Delivery: at-least-once. A crash between NATS publish and marking the row
  published re-publishes the event on restart.
- Duplicates: publishes use `Nats-Msg-Id: <event_id>`; JetStream de-dupes
  within its window, and consumers MUST be idempotent on `event_id` anyway.
"""

import asyncio
import json
from typing import Protocol

import nats
from sqlalchemy import select

from agora_api.config import get_settings
from agora_api.db import session_factory
from agora_api.events import envelope_dict, now_utc
from agora_api.logging import get_logger
from agora_api.models import Event, EventOutbox

log = get_logger("agora.api.publisher")

STREAM_NAME = "AGORA_EVENTS"
STREAM_SUBJECTS = ["agora.events.>"]


class EventPublisher(Protocol):
    """Event Publisher boundary — NATS today, swappable later."""

    async def publish(self, subject: str, body: bytes, msg_id: str) -> None: ...


class NatsPublisher:
    def __init__(self) -> None:
        self._nc: nats.NATS | None = None

    async def connect(self) -> None:
        self._nc = await nats.connect(get_settings().nats_url)
        js = self._nc.jetstream()
        try:
            await js.add_stream(name=STREAM_NAME, subjects=STREAM_SUBJECTS)
        except Exception:
            pass  # stream already exists

    async def publish(self, subject: str, body: bytes, msg_id: str) -> None:
        assert self._nc is not None, "publisher not connected"
        js = self._nc.jetstream()
        await js.publish(subject, body, headers={"Nats-Msg-Id": msg_id})

    async def close(self) -> None:
        if self._nc is not None:
            await self._nc.drain()
            self._nc = None


class OutboxDrainer:
    """Background task: drains unpublished outbox rows to the publisher."""

    def __init__(self, publisher: NatsPublisher) -> None:
        self.publisher = publisher
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        await self.publisher.connect()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task
        await self.publisher.close()

    async def _run(self) -> None:
        interval = get_settings().outbox_poll_interval_seconds
        while not self._stop.is_set():
            try:
                drained = await self.drain_once()
                if drained:
                    continue  # keep draining while there is work
            except Exception as exc:
                log.error("outbox.drain_failed", error=str(exc))
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except TimeoutError:
                pass

    async def drain_once(self, batch_size: int = 100) -> int:
        async with session_factory()() as session:
            rows = (
                await session.execute(
                    select(EventOutbox)
                    .where(EventOutbox.published.is_(False))
                    .order_by(EventOutbox.outbox_id)
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).scalars().all()
            for row in rows:
                event = await session.get(Event, row.event_id)
                assert event is not None
                body = json.dumps(envelope_dict(event)).encode()
                await self.publisher.publish(row.subject, body, msg_id=event.event_id)
                row.published = True
                row.published_at = now_utc()
            await session.commit()
            return len(rows)
