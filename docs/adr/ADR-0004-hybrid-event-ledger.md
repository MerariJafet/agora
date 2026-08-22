# ADR-0004: Hybrid event ledger + current-state projections

Status: Accepted · Date: 2026-08-22

## Decision
Public history is an append-only `events` ledger (immutable via app
convention AND Postgres triggers). Query surfaces read separate mutable
projection tables (`agents`, `devices`, ...). Event publication to NATS
JetStream goes through a transactional outbox written in the same DB
transaction as the state change.

## Rationale
- Provenance and attributability need an immutable record (constitution 7, 8).
- Full event-sourcing (rebuild-everything) is premature; projections written
  transactionally with events give current-state reads at O(1) without replay
  infrastructure.
- Outbox prevents the classic dual-write divergence between DB and broker.

## Delivery semantics
At-least-once. Ordering per insertion (`outbox_id`); consumers must be
idempotent on `event_id` (ULID, time-sortable). JetStream dedups via
`Nats-Msg-Id`. Heartbeat/presence noise is banned from the ledger — it goes
to Redis/NATS ephemeral subjects only.

## Consequences
- A crash between publish and mark-published re-publishes (safe by idempotency).
- Later replay/projection-rebuild tooling can be added without schema change.
