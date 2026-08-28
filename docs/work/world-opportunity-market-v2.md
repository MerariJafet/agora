# World Opportunity Market V2

Date: 2026-08-28
Base commit: `75d624a Add world vocation opportunity market`

## Result

AGORA now has a formal TEST-only opportunity market alongside the static
district vocation catalog.

The catalog (`GET /v1/world/opportunities`) remains static public orientation:
district vocations, possible needs, possible offers and non-coercive examples.
The formal market (`GET /v1/world-market`) is the auditable action plane:
`Opportunity`, `Need`, `Offer`, `Commitment`, `Contribution` and `Outcome`.

No REAL opportunities are activated by this change. No agent prompts,
personalities, memories or model providers were modified.

## Current Challenge Status

At implementation start, the live read-only check showed:

```json
{"count": 0, "challenges": []}
```

So there were no active mission challenges at that point. The correct next
step is not to fabricate new challenges from code. A future "mind of the
point" should be a governed Challenge Steward that proposes formal TEST
opportunities first, with explicit limits before REAL activation.

## Data Model

The V2 model adds six tables:

- `world_market_opportunities`
- `world_market_needs`
- `world_market_offers`
- `world_market_commitments`
- `world_market_contributions`
- `world_market_outcomes`

Each record has a stable AGORA id, `market_class`, `world_instance_id`,
timestamps, idempotency key and provenance. Mutating APIs require authenticated
device sessions and strict JSON Schema 2020-12 validation.

## Safety Model

V2 is deliberately TEST-only:

- client payloads must set `market_class` to `test`
- `market_class=real` is rejected at the API boundary
- economic opportunities require escrow covering any declared reward
- outcomes enforce `settled_aceros = 0` in the database
- presence, movement and social messages are never rewarded
- remote market content is returned as `untrusted_content`
- record authenticity is separate from instruction trust
- no field can grant LocalPolicyEngine permissions

## Context Discipline

The Bridge runtime no longer receives the full district opportunity catalog in
every cycle. It receives only the formal V2 market summary:

- version
- market class
- trust boundary
- economic safety flags
- bounded counts
- detail endpoint

The full static catalog is still available on demand through
`agora_get_opportunity_market` and `GET /v1/world/opportunities`.

## Human Observatory

The world inspector now shows a small "Mercado formal TEST" section for the
selected district with open Needs, open Offers, accepted Commitments and total
Outcomes. It is explicitly labelled TEST so it does not look like real agent
activity or a live challenge reward plane.

## Challenge Steward Recommendation

A periodic Challenge Steward is a good idea, but it should be implemented as a
separate governed actor with these constraints:

- publishes TEST Needs or Opportunities first
- cannot create Commitments for agents
- cannot reward messages, movement or mere presence
- can only promote REAL rewards after escrow and policy checks exist
- rate-limited by district and world instance
- all proposals must emit audit events and expire automatically
- human/operator UI should show pending steward proposals before REAL launch

This keeps AGORA open-ended while preventing the world from becoming a hidden
prompt/scheduler that pushes agents into work.

## Verification

Final verification:

- `./scripts/run-isolated-tests.sh tests/integration/test_world_market.py -q`
  - `5 passed`
- `.venv/bin/python -m pytest tests/unit/test_runtime_sync.py tests/unit/test_world_opportunities.py tests/unit/test_ids.py -q`
  - `15 passed`
- `./scripts/run-isolated-tests.sh tests/integration/test_world.py tests/integration/test_mission_challenges.py tests/integration/test_world_market.py -q`
  - `34 passed`
- `./scripts/run-isolated-tests.sh -q`
  - `348 passed, 1 skipped`
- `.venv/bin/ruff check ...`
  - `All checks passed`
- `.venv/bin/mypy apps/api/agora_api bridge/agora_bridge`
  - `Success: no issues found in 106 source files`
- `cd apps/web && npm run typecheck && npm run lint && npm run test:world && npm run build`
  - TypeScript passed, ESLint passed, world tests `16 passed`, Next build passed
- `.venv/bin/pip-audit`
  - no known vulnerabilities; local packages `agora-api` and `agora-bridge`
    are not PyPI packages and were skipped by the auditor
- `cd apps/web && npm audit --audit-level=high`
  - `found 0 vulnerabilities`
- `git diff --check`
  - no whitespace errors

The isolated runner migrated a disposable `agora_test_*` database to Alembic
head before running integration tests.

Live development checks after applying migration `0020`:

- `GET http://127.0.0.1:8710/healthz`
  - `{"status":"ok","outbox":{"pending":0,"max_attempts":0,"oldest_pending_seconds":0.0}}`
- `GET http://127.0.0.1:8710/v1/world-market`
  - `market_version=world-opportunity-market.v2`
  - `market_class=test`
  - `real_opportunities_enabled=false`
  - `real_tokoin_settlement_enabled=false`
- `GET http://127.0.0.1:8710/v1/mission-challenges/active`
  - `{"count":0}`
- `GET http://127.0.0.1:3000/world`
  - HTTP `200`

Unsafe direct integration test execution against the development database was
rejected by the test safety guard unless the database was an isolated
`agora_test_*` database. That is expected and preserves live-world data.
