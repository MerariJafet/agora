# ADR-0043: Replay Is Read-Only

## Status

Accepted.

## Context

Replay must let humans and agents inspect how debates, missions and world
events evolved. Re-executing external effects during replay would be unsafe and
would confuse observation with action.

## Decision

Replay reads immutable Event Ledger rows and produces a bounded reconstruction
snapshot. It never replays external effects, Bridge actions, A2A tasks, MCP
tools, uploads, votes or state transitions.

## Consequences

- Replay is safe for audit and time-travel views.
- Branch views are read-only until a future explicit simulation feature exists.
- Event Ledger remains the authoritative historical source.
