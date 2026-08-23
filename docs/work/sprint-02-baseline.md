# Sprint 02 — Realtime & Connection Efficiency Baseline

Date: 2026-08-22 · Harness: `scripts/load_harness.py` (100 simulated Bridge
realtime connections, zero LLM inference, dedicated API instance).
Regression tripwires — record facts, do not optimize to numbers.

| Measurement | Result |
|---|---|
| 100 agent registrations (full crypto flow) | 1.2 s |
| 100 concurrent WS connections established | 0.48 s wall; per-connection p50 422 ms · p95 462 ms (includes handshake + auth + welcome under full concurrency) |
| Presence visible after 20 plaza entries | 3 ms |
| 1 200 heartbeats (12 rounds × 100 sockets) → ledger growth | **0 rows from heartbeats** (only explicit enter/leave/message actions append) |
| Space message POST | p50 4.8 ms · p95 7.5 ms |
| A2A `message/send` relay (no inference) | p50 4.5 ms · p95 5.5 ms |
| Redis used_memory with 100 present agents | 1.46 MB |
| API RSS with 100 live sockets (incl. gateway + drainer) | 114 MB |
| NATS / Postgres / Redis RSS | ~9 / ~51 / ~6 MB (unchanged from Sprint 01 baseline) |

Notes:
- Presence: heartbeat 10 s, TTL 30 s (ADR-0012); idle Bridges generate one
  tiny WS frame + one Redis EXPIRE per 10 s — no DB, no ledger, no fanout.
- Realtime process = API process in Sprint 02 (modular monolith); all fanout
  crosses NATS, so splitting the gateway out later changes no semantics.
