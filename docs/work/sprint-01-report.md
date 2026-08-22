# AGORA — Sprint 01 Completion Report (Secure Foundation)

Status: **DONE** · Date: 2026-08-22 · Branch: `feat/agora-sprint-01-foundation`

## Executive summary

The complete secure vertical slice works end to end: AGORA Bridge generates an
Ed25519 identity locally (OS keyring), completes challenge-response
registration against AGORA API, the Agent+Device persist transactionally with
immutable `agent.registered` / `device.authorized` ledger events published to
NATS JetStream via a transactional outbox, the Next.js Central Plaza renders
the agent with an Agent Inspector and working Revoke, and a revoked device is
denied on every subsequent authenticated call. No private key or provider
credential ever crosses the wire — enforced structurally (schemas without a
key slot, unknown fields rejected) and verified by automated SEC tests.
36 tests green, ruff/mypy/tsc/eslint clean, dependency scans clean
(Next.js was upgraded 15.4.7 → 16.3.2 specifically to clear critical
advisories), full gate re-run from destroyed volumes + empty database.

## Test results

| Suite | Count | Notes |
|---|---|---|
| unit | 20 | crypto, ids, boundary schemas, policy, budget, audit |
| integration | 9 | real Postgres/Redis: happy path, expiry, single-use, replay, malformed sig, idempotency, name conflict, unknown fields, rate limit ×2 |
| security | 6 | SEC-001/002/003/006/007 + ledger immutability (DB triggers) |
| e2e | 1 | Genesis Agent full lifecycle (boots own uvicorn, drives real CLI) |
| **total** | **36 passed / 0 failed** | plus manual Genesis run + browser verification |

## Security invariants

All eight SEC invariants have automated tests (see docs/threat-model.md table).
Threats found & fixed during self-review: none open; the port-5433 collision,
the event-loop test bug and the Next.js advisories were fixed in-sprint.
Remaining risks (documented, accepted for dev): no TLS locally, revoke
endpoint unauthenticated until owner accounts, no challenge GC job,
agent-name squatting until user accounts.

## Performance baseline

See docs/work/sprint-01-baseline.md — 45.9 reg/s full-flow (p95 36.8 ms),
`GET /v1/agents` p95 3.7 ms at 64 agents (2 queries, no N+1); API 99 MB RSS,
Postgres 51 MB, Redis 6 MB, NATS 9 MB.

## Deviations from the sprint prompt

1. Postgres host port 5434 (5433 occupied on this machine).
2. Single repo-root Python venv for api+bridge+tests (documented in README).
3. A2A/MCP SDK versions not pinned — no SDK code ships in Sprint 01
   (adapter interfaces only); pinning happens with first real integration
   per ADR-0002/0003 verification rule.
4. Idempotent registration replays return fresh session tokens (original
   tokens are never stored in plaintext) — strictly safer than literal replay.

## Technical debt

- Challenge/session expiry garbage collection job.
- Event `signature` field populated only when agent-authored content arrives.
- `agora pause` is local-only (no cloud presence effect yet — no live
  connection concept until the sockets/presence sprint).
- Web e2e coverage is API-level; no Playwright yet.
- launch of `usr_` User accounts (table + authz) deferred to identity sprint.

## Sprint 02 preconditions (recommended)

1. Review this report + threat model residual risks.
2. Decide the owner-account/authn provider direction (interface exists).
3. Presence/connection model (Redis TTL + NATS ephemeral) before any social feature.
4. Pin A2A SDK against current official docs when starting agent-to-agent work.
