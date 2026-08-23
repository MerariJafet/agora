"""Event consumer idempotency.

Delivery from the outbox → NATS JetStream is AT-LEAST-ONCE. Every consumer
of `agora.events.>` MUST deduplicate on the stable `event_id` before applying
side effects.

Two implementations:
- `IdempotentConsumer` — in-memory, for single-process ephemeral consumers
  (e.g. a realtime fanout loop whose state dies with its connections).
- `DurableConsumer` (S2-T01) — Postgres-backed via `processed_events`.
  Uniqueness is enforced by the composite primary key at persistence level,
  and the dedup mark shares ONE transaction with the consumer's side effect:
  * crash before commit  → nothing marked, redelivery reprocesses (safe);
  * crash after commit but before broker ack → redelivery hits the conflict
    and is skipped (no duplicate side effect);
  * process restart cannot forget what was processed.
  This is at-least-once + durable idempotency, NOT global exactly-once.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.models import ProcessedEvent


class IdempotentConsumer:
    """Applies each logical event exactly once per consumer identity,
    regardless of how many times NATS delivers it."""

    def __init__(self, name: str, apply: Callable[[dict[str, Any]], None]):
        self.name = name
        self._apply = apply
        self._seen: set[str] = set()
        self.duplicates_skipped = 0

    def handle(self, envelope: dict[str, Any]) -> bool:
        """Returns True when the event was applied, False when deduplicated."""
        event_id = envelope["event_id"]
        if event_id in self._seen:
            self.duplicates_skipped += 1
            return False
        # Mark BEFORE apply: an at-least-once redelivery during a crash makes
        # the event re-arrive anyway; apply() must therefore stay atomic per
        # event. For DB-backed consumers, seen-marking and side effect share
        # one transaction.
        self._seen.add(event_id)
        self._apply(envelope)
        return True


class DurableConsumer:
    """Persistence-backed idempotent consumer (see module docstring)."""

    def __init__(
        self,
        name: str,
        session_factory: Callable[[], AsyncSession],
        apply: Callable[[AsyncSession, dict[str, Any]], Awaitable[None]],
    ):
        self.name = name
        self._session_factory = session_factory
        self._apply = apply
        self.duplicates_skipped = 0

    async def handle(self, envelope: dict[str, Any]) -> bool:
        """Apply the event exactly once per consumer identity. Returns True
        when applied, False when deduplicated. Mark + side effect commit
        atomically in one transaction."""
        from agora_api.events import now_utc

        event_id = envelope["event_id"]
        async with self._session_factory() as session:
            marked = await session.execute(
                pg_insert(ProcessedEvent)
                .values(consumer_name=self.name, event_id=event_id, processed_at=now_utc())
                .on_conflict_do_nothing(index_elements=["consumer_name", "event_id"])
            )
            if (getattr(marked, "rowcount", 0) or 0) == 0:
                self.duplicates_skipped += 1
                return False
            await self._apply(session, envelope)
            await session.commit()
            return True
