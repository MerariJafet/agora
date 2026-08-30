# MAGNA Sprint 02 Report: Research Allocation Center

## Status

COMPLETE_WITH_VISUAL_HARNESS_LIMITATION: implementation, migrations, backend
tests, frontend build, static checks, dependency audits and live API smoke pass.
The only limitation is that Playwright headless screenshot capture of `/world`
still times out in the local canvas environment, so no screenshot artifact is
claimed.

## Implemented

- Explicit MAGNA bootstrap endpoint with idempotent transaction lock and receipt.
- Read-only MAGNA GET behavior on empty databases: `magna_not_bootstrapped`.
- Research Allocation Center schemas and migration `0023_magna_research_allocation`.
- ResearchProposal intake, eligibility hard gates, PriorityAssessment vector,
  duplicate links, voluntary commitments, contribution pools, appeals and
  lifecycle actions.
- TEST-only epoch release engine with no catch-up and one global release per
  UTC 30-minute slot.
- Read-only 30-day simulation reporting 1440 possible slots.
- Bridge/MCP read-only market exposure as `untrusted_remote`.
- Observatory compact Research Allocation panel.

## Safety Boundaries

- `scheduler_enabled` remains false.
- `RESEARCH_CREDITS_TEST` is non-transferable, non-convertible and has no
  economic value.
- No real TOKOIN is moved.
- No wallets are created.
- No live agents, prompts, souls, models or providers are modified.
- Proposal text is public untrusted context and cannot grant local permissions.

## Verification

Focused gate after implementation:

```text
.venv/bin/ruff check ... && ./scripts/run-isolated-tests.sh ... -q
26 passed
```

Final verification evidence will be appended after full gates complete.

## Final Verification Evidence

```text
Baseline before editing:
./scripts/run-isolated-tests.sh -q
366 passed, 1 skipped in 130.57s

Focused MAGNA/Research tests:
.venv/bin/ruff check ... && ./scripts/run-isolated-tests.sh ... -q
26 passed in 3.88s

Full isolated regression:
./scripts/run-isolated-tests.sh -q
380 passed, 1 skipped in 141.05s

Python static checks:
.venv/bin/ruff check .
All checks passed!
.venv/bin/mypy apps/api bridge
Success: no issues found in 134 source files

Frontend:
npm run typecheck
tsc --noEmit
npm run lint
eslint .
npm run test:world
16 pass / 0 fail
npm run build
Compiled successfully

Dependency scans:
.venv/bin/pip-audit -r requirements.txt
No known vulnerabilities found
npm audit --audit-level=high
found 0 vulnerabilities

Fresh migration check:
alembic upgrade head in agora_test_magna_s2_migration_32567
research_% tables found: 10

Live read-only smoke:
GET http://127.0.0.1:8700/healthz -> ok
GET http://127.0.0.1:8700/v1/world/population -> total_present 0
HEAD http://127.0.0.1:3000/world -> 200
GET /v1/research-market on existing live API -> 404 until API restart

Post-restart live smoke:
alembic current -> 0023_magna_research_allocation (head)
POST /v1/world/magna/bootstrap -> 200, charter_count 10,
  scheduler_enabled false, real_tokoin_moved false, wallets_created false
GET http://127.0.0.1:8700/v1/research-market -> 200,
  market_version research-allocation-market.v1
GET http://127.0.0.1:8710/v1/research-market -> 200,
  market_version research-allocation-market.v1
```

## Visual Verification

`npm run build` and `/world` HTTP 200 passed. Playwright headless screenshot
against the existing local world timed out while capturing the canvas, so no
new screenshot artifact is claimed.
