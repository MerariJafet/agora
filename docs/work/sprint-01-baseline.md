# Sprint 01 — Performance & Efficiency Baseline

Date: 2026-08-22 · Environment: local dev (Linux, 62 GB RAM, Docker Compose
infra, uvicorn single worker, `next dev`). Reproduce with the script pattern
in this doc's history or re-run: 30 sequential full registration flows +
50× read probes against a warm API.

These are regression tripwires, not targets. Later sprints compare against
this table; they do NOT optimize toward arbitrary numbers.

## Throughput / latency (single client, sequential)

| Operation | Result |
|---|---|
| Full registration flow (challenge + local Ed25519 sign + register, 2 HTTP calls, 4 ledger/outbox writes) | **45.9 reg/s**; avg 21.7 ms · p50 16.6 ms · p95 36.8 ms |
| `GET /v1/agents` (64 agents, devices aggregated, 2 queries total — no N+1) | avg 3.3 ms · p50 3.2 ms · p95 3.7 ms |
| `GET /healthz` (live Postgres + Redis checks) | avg 1.9 ms · p50 1.9 ms · p95 2.2 ms |

## Memory footprint (RSS)

| Service | Memory |
|---|---|
| AGORA API (uvicorn, 1 worker) | 99 MB |
| PostgreSQL 16 (container) | 51 MB |
| Redis 7 (container) | 6 MB |
| NATS 2.10 JetStream (container) | 9 MB |
| Web `next dev` (dev mode — not representative of prod `next start`) | ~446 MB |

## Efficiency posture (S1-T14 checklist)

- No polling loops except the outbox drainer (0.5 s interval, single indexed
  query on `(published, outbox_id)`, batch 100, drains continuously under load).
- No N+1 in list/status endpoints (`/v1/agents` = 2 queries regardless of N).
- No heartbeats in the ledger: `devices/ping` updates a projection column only.
- No model inference anywhere in AGORA Cloud.
- No pixel/world movement persisted anywhere.

## Ephemeral vs persistent (guidance recorded for future world state)

- **Ledger (Postgres, forever):** registrations, revocations, agent version
  changes, future artifacts/missions outcomes.
- **Projections (Postgres, mutable):** agent/device current state, last_seen.
- **Ephemeral (Redis/NATS only, TTL):** presence, rate-limit windows, future
  plaza positions/animation state, in-flight negotiation. Idle locations must
  hold zero scheduled work.
