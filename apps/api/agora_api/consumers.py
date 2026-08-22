"""Event consumer idempotency (S1.1-T04).

Delivery from the outbox → NATS JetStream is AT-LEAST-ONCE. Every consumer
of `agora.events.>` MUST deduplicate on the stable `event_id` before applying
side effects. `IdempotentConsumer` is the reference implementation and base
class for future materializers (world state, notifications, search indexes).

Sprint 01.1 keeps the seen-set in memory per consumer instance; durable
consumers (a Postgres `consumer_offsets`/`processed_events` table) arrive
with the first cross-process consumer in a later sprint — the contract
(`dedupe on event_id`) is identical.
"""

from collections.abc import Callable
from typing import Any


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
