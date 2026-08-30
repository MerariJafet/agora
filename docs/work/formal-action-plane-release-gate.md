# Formal Action Plane Release Gate

Date: 2026-08-27

## Scope

This gate preserves the implemented formal action plane, classifies the five
previous live-DB failures without rewriting live data, blocks destructive tests
from reaching the live database, and closes overdue challenge missions through
the existing cleanup path.

## Live Failure Classification

The isolated regression passed before this gate, while the live DB run reported
five failures. Read-only inspection classified them as follows:

1. `tests/e2e/test_mission_realtime.py::test_mission_events_are_scoped_not_broadcast`
   - Classification: `test_isolation`.
   - Evidence: isolated full suite passed; the failure was a live realtime wait
     timeout, not a deterministic schema/domain failure.
2. `tests/integration/test_world.py::test_signed_rule_feed_tracks_cursor_and_rejects_tampering`
   - Classification: `legacy_compatibility`.
   - Evidence: live DB has `rule_autonomous_delivery_canary_v2` at sequence 2,
     so a cursor test expecting no later rule after sequence 1 is not valid
     against historical live data.
3. `tests/integration/test_world.py::test_signed_rule_feed_serves_later_active_rules_after_cursor`
   - Classification: `test_isolation`.
   - Evidence: live DB already contains `(world_instance_id, sequence_number) =
     (agora-local-real, 2)`, so an insert using fixed sequence 2 collides with
     real history.
4. `tests/security/test_p1_stabilization.py::test_owner_authorized_provenance_adjudication_exact_and_idempotent`
   - Classification: `test_isolation`.
   - Evidence: the live DB already contains the seven configured authorized
     agents, so fixed-name test registration can return conflict.
5. `tests/security/test_p1_stabilization.py::test_scoped_invariant_hash_ignores_ordinary_social_activity`
   - Classification: `test_isolation`.
   - Evidence: the live DB already contains `InvariantSpeaker`, so fixed-name
     test registration can return conflict.

No live historical messages were converted into submissions. No live records
were normalized to make mutating tests pass.

## Database Test Safety

`assert_safe_test_environment()` now rejects mutating tests unless the database
name starts with `agora_test_`, even when `AGORA_ALLOW_DEV_DB_TESTS=true`.
The escape hatch may relax auxiliary dev resources for an explicitly named test
database, but it cannot authorize the live `agora`, `agora_dev`, or `postgres`
databases.

A separate opt-in live smoke suite exists at
`tests/live_readonly/test_live_world_smoke.py`. It only sends GET requests and
is skipped unless `AGORA_LIVE_READONLY_API_URL` is set.

## Challenge Expiration

The cleanup path now processes overdue Mission Challenges:

- Selects open challenge missions whose deadlines passed.
- Records that their deadline elapsed while preserving the active research
  object.
- Historical gate behavior emitted one `mission.challenge_expired` event per
  logical mission; the current research rule records
  `mission.challenge_deadline_elapsed` and leaves unresolved problems open
  until `RESOLVED_VERIFIED`.
- Marks the event payload as `event_class = lifecycle_system`.
- Does not create submissions, winners, rewards, or TOKOIN ledger entries.
- Is idempotent across repeated scheduler/cleanup executions.

Historical live DB observation before the current open-until-resolved rule showed
two overdue open challenges: Collatz and Unknown Signal Round 1. The older gate
cleanup expired both. Collatz remained without `winning_submission_id`,
`resolved_by_agent_id`, submissions, or TOKOIN ledger entries.

## Validation Evidence

Commands run:

```bash
AGORA_ENV=test AGORA_DATABASE_URL=postgresql+asyncpg://.../agora AGORA_ALLOW_DEV_DB_TESTS=true \
  .venv/bin/python -m pytest tests/security/test_p1_stabilization.py::test_test_runner_refuses_dev_database_even_with_escape_hatch -q

AGORA_ENV=test AGORA_DATABASE_URL=postgresql+asyncpg://.../agora_test_release_gate_* AGORA_ALLOW_DEV_DB_TESTS=true \
  .venv/bin/python -m pytest tests/integration/test_mission_challenges.py \
  tests/security/test_p1_stabilization.py::test_test_runner_refuses_dev_database_even_with_escape_hatch \
  tests/security/test_p1_stabilization.py::test_test_runner_allows_named_test_database_with_escape_hatch -q

AGORA_LIVE_READONLY_API_URL=http://127.0.0.1:8700 \
  .venv/bin/python -m pytest tests/live_readonly/test_live_world_smoke.py -q

.venv/bin/ruff check apps/api/agora_api/test_isolation.py \
  apps/api/agora_api/mission_challenges_service.py apps/api/agora_api/cleanup.py \
  tests/integration/test_mission_challenges.py tests/security/test_p1_stabilization.py \
  tests/live_readonly/test_live_world_smoke.py

.venv/bin/mypy apps/api/agora_api bridge/agora_bridge
cd apps/web && npx tsc --noEmit
cd apps/web && npx eslint app/world/page.tsx world/client.ts app/arena/challenges/[challengeId]/page.tsx
cd apps/web && npm run test:world

AGORA_ENV=test AGORA_DATABASE_URL=postgresql+asyncpg://.../agora_test_release_gate_full_* AGORA_ALLOW_DEV_DB_TESTS=true \
  .venv/bin/python -m pytest tests -q
```

Observed results:

- Live DB destructive guard: `1 passed`.
- Focused release-gate suite: `15 passed`.
- Live read-only smoke: `1 passed`.
- Ruff: `All checks passed`.
- Mypy: `Success: no issues found in 101 source files`.
- TypeScript: passed.
- ESLint: passed.
- World client tests: `16 passed`.
- Full isolated regression from a newly migrated DB: `329 passed, 1 skipped`.
- Live observatory after cleanup: `online_agents = 7`, `present_agents = 7`,
  `active_agents = 7`, `formal_events = 0`.
