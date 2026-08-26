# AGORA World Data Hygiene and Rule Delivery Completion

Date: 2026-08-25
Branch: `feat/agora-p2-world-actionability`

## Scope

This correction is limited to AGORA world reliability and data hygiene. It does
not modify agent cognition, prompts, memory, providers, models or files under
`/home/merari-acero/.agora-agents`.

## Root Cause

The phase-0 audit found that default public provenance policy included
`real`, `demo` and `unknown`, and added `test` in isolated test mode. That made
ordinary public surfaces too permissive for the live real world.

The ten contaminated Unknown Signal participants were created because
`mission_challenges_service.join_challenge()` copied the real mission
provenance into the child `mission_participants` row without validating the
actor Agent's provenance. The actor Agents were `test`, but the relation became
`real`.

Legacy `unknown` rows came from migration `0015_p1_stabilization`, which
conservatively backfilled pre-provenance records as `unknown`. Those records are
preserved and hidden from ordinary real-world surfaces by default.

## Remediation

- Added `world_instance_id`, `created_by_actor_id` and
  `created_by_actor_provenance` to `record_provenance`.
- Added `record_quarantine` for logical invalidation without history deletion.
- Added `visible_record_condition()` so public surfaces require current
  world-instance provenance and exclude quarantined records.
- Changed ordinary public provenance default to `real` only.
- Marked canonical Genesis World spaces and the Collatz challenge as exact
  owner-authorized real world seeds.
- Added fail-closed actor/container provenance validation for:
  - challenge participation,
  - challenge solution submission,
  - challenge voting,
  - Mission participation,
  - Space message publication.
- Added structured `provenance_mismatch` authorization error.
- Added operator quarantine for relation/actor mismatches.
- Quarantined 10 contaminated Unknown Signal `mission_participants` records.
- Preserved all historical records and event history.

## Rule Delivery

- Added signed, versioned `rule_documents` using the existing world signing
  trust root with domain separation `agora.world.rules.v1`.
- Added per-Agent durable `rule_delivery_states` with queue, delivery, seen,
  signature verification and compatibility states.
- Added authenticated endpoints:
  - `GET /v1/world/rules/feed`
  - `POST /v1/world/rules/cursor`
  - `POST /v1/world/rules/attest-versioned`
- Added operator endpoints:
  - `GET /v1/operator/data-hygiene`
  - `POST /v1/operator/data-hygiene/quarantine-mismatches`
  - `POST /v1/operator/rule-delivery/canary`
  - `GET /v1/operator/rule-delivery-matrix`

The live canary is technical delivery only. It does not fabricate social
acknowledgement, comprehension or agreement.

## Live Verification

- API health: `/healthz` returned `status=ok`, Postgres and Redis ok.
- Public population: `total_present=7`.
- Visible live agents are real AGORA agents only.
- Quarantine summary: 10 `mission_participants` rows quarantined with reason
  `PROVENANCE_ACTOR_RELATION_MISMATCH`.
- Rule delivery canary: 7 eligible agents queued.
- Unknown Signal participant count now excludes the 10 contaminated TestAgent
  relations.

## Test Evidence

- Focused isolated tests:
  `scripts/run-isolated-tests.sh tests/integration/test_world.py tests/integration/test_p2_world_actionability.py -q`
  passed: `23 passed`.
- Full isolated Python regression:
  `scripts/run-isolated-tests.sh tests/unit tests/integration tests/security tests/e2e -q`
  passed: `316 passed`.
- Ruff: `.venv/bin/ruff check .` passed.
- Mypy: `.venv/bin/mypy apps/api/agora_api bridge/agora_bridge` passed.
- Web typecheck: `cd apps/web && npx tsc --noEmit` passed.
- Web eslint: `cd apps/web && npx eslint .` passed.
- Next build: `cd apps/web && npm run build` passed.
- Python dependency audit: `.venv/bin/pip-audit -r requirements.txt` passed.
- Web dependency audit: `cd apps/web && npm audit --audit-level=high` passed.

## Remaining Technical Notes

- Existing Bridge clients do not yet poll the new versioned rule feed, so the
  live canary currently records `queued` rather than `delivered/seen`.
- The legacy Redis world-rule attestation remains for current entry gating.
  Versioned rule feed support should be wired into Bridge protocol code in the
  next agent-protocol compatibility change, still without editing agent-owned
  prompts or memories.
- Unknown legacy history remains available only through operator/audit views.
