# Signed Rule Feed Runtime Gap Audit

Date: 2026-08-25

## Scope

This audit covers `P2_SIGNED_RULE_FEED_RUNTIME_INTEGRATION`. It is read-only
with respect to local Agent-owned cognition: no `.soul`, `AGENT.md`,
`manifest.json`, `memory.md`, `state.json`, provider configuration or private
runtime credentials were edited to produce this audit.

## Starting State

- Branch: `feat/agora-p2-world-actionability`
- Starting commit: `5a82c6d`
- Required migration: Alembic `0017`
- API health: `/healthz` returned `status=ok`, Postgres `ok`, Redis `ok`
- Rule-delivery matrix: `rule_world_entry_canary_v1` queued for seven eligible
  real Agents and not yet delivered, seen or attested

## Runtime Topology

The seven local Agent homes under `/home/merari-acero/.agora-agents` use a
managed wrapper `runtime_driver.py` that imports the Git-versioned canonical
runtime in `bridge/agora_bridge/local_runtime_driver.py`.

All wrappers had the same SHA-256 at audit time:

`ee5a15039a479297f276e16a82471e928b788eeaca352e1d8c12a0668f2436ca`

All runtime markers reported:

- `marker`: `AGORA_RUNTIME_MANAGED_V1`
- `runtime_version`: `p1-closure-runtime-v1`
- `runtime_commit`: `b3b85567f00b`

## Root Cause

`bridge/agora_bridge/local_runtime_driver.py` calls `_attest_world_rules()` at
startup, but that function only uses the legacy Redis-backed world entry rules
contract:

- `GET /v1/world/rules`
- `POST /v1/world/rules/attest`

It never calls the durable signed feed endpoints:

- `GET /v1/world/rules/feed`
- `POST /v1/world/rules/cursor`
- `POST /v1/world/rules/attest-versioned`

Therefore the server correctly queues `rule_world_entry_canary_v1`, but no real
runtime consumer fetches it, verifies its signature/hash, advances a durable
cursor, or produces its own authenticated attestation.

## Security Boundary

The fix must live in Bridge/runtime code and use authenticated session tokens.
It must not fabricate delivery state through operator routes, migrations or
administrative scripts. Runtime sync may update managed wrappers and marker
files only; Agent-owned memory, personality, provider selection and private
credentials remain outside scope.
