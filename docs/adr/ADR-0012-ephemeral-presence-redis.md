# ADR-0012: Ephemeral Presence in Redis

Status: Accepted · Date: 2026-08-22

## Decision
Presence lives exclusively in Redis with TTLs: key
`presence:{space_id}:{agent_id}` (+ agent→space pointer), TTL **30 s**,
refreshed by a Bridge heartbeat every **10 s** over the realtime connection.

- Heartbeats NEVER touch the immutable Event Ledger (SEC-010; verified by
  test and by the 1 200-heartbeat harness run: 0 ledger rows).
- Explicit enter/leave are semantically meaningful actions and DO append
  `space.entered` / `space.left` ledger events.
- A crashed Bridge simply stops refreshing and expires to offline ≤30 s
  later; recovery needs no database repair — presence is derivable state.
- Nothing in Redis is a source of truth.

## Consequences
- Idle world cost approaches zero: an idle location holds only expiring keys.
- Presence reads use SCAN over the space prefix — fine at Sprint 02 scale;
  a Space-sharded set structure is the known upgrade path if needed.
