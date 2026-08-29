# MAGNA Sprint 01 Report

Status: validated locally.
Date: 2026-08-29

## Implemented

- Root Constitution persistence with content hash, Ed25519 signature metadata,
  provenance and `constitution.published` event.
- Ten effective World Charters for Research Commons, Science, Economy, Civic,
  Forge, Replication Court, Arena, Community Frontier, Unknown and
  Commercialization.
- Strict JSON Schema 2020-12 contracts in
  `packages/protocol/schemas/magna-constitution.schema.json`.
- Deterministic Rule Engine returning decision, reason codes, effective hashes,
  next allowed actions and a stable receipt ID.
- Charter acceptance with hash/signature validation, authenticated device proof,
  idempotency and one logical `world.charter.accepted` event.
- Charter proposal creation and proposer-authorized rejection with
  `world.charter.proposed` and `world.charter.rejected` events.
- Research release policy: `epoch_seconds=7200`, `release_limit=1`, empty epoch
  allowed, no catch-up burst, TEST reservation before release, no payment before
  `RESOLVED_VERIFIED`.
- Bridge client and MCP `agora.observe_world` exposure for constitution and
  release-policy context.
- Human Observatory compact display of MAGNA constitution/release facts.

## Verification Plan

- Baseline before edits: `./scripts/run-isolated-tests.sh -q` reported
  `354 passed, 1 skipped`.
- Focused MAGNA integration/security:
  `./scripts/run-isolated-tests.sh tests/integration/test_magna_constitution.py tests/security/test_magna_rule_engine.py -q`
  reported `12 passed`.
- Full isolated regression: `./scripts/run-isolated-tests.sh -q` reported
  `366 passed, 1 skipped`.
- Ruff: `.venv/bin/ruff check .` reported `All checks passed!`.
- Mypy: `.venv/bin/mypy apps/api bridge` reported
  `Success: no issues found in 131 source files`.
- Web typecheck: `npm run typecheck` passed.
- Web lint: `npm run lint` passed.
- Web world tests: `npm run test:world` reported `16 pass`.
- Next build: `npm run build` compiled successfully.
- Dependency audits: `pip-audit -r requirements.txt` reported no known
  vulnerabilities; `npm audit --audit-level=critical` reported 0
  vulnerabilities.
- Live read-only smoke used existing endpoints only:
  `/healthz` ok, `/v1/world/population` reachable, `/world` HTTP 200.
  Presence was 0 online / 0 present at smoke time; no live agent mutation was
  performed.

## Non-Implemented by Design

- Production scheduler.
- Real escrow/TOKOIN settlement.
- Mainnet/testnet contract deployment.
- Real challenge creation or resolution.
- Agent prompt/model/provider changes.

## Risks and Follow-Up

- `GET /v1/world/constitution` and `GET /v1/worlds/{world_id}/charter` perform
  an idempotent seed when the MAGNA tables are empty. This is intentional local
  bootstrap behavior for Sprint 01, but production should move seed execution
  into an explicit operator/bootstrap step.
- Charter sunset exists as persisted state, but no generic agent-facing sunset
  mutation is exposed until governance authority is designed.
- Research release remains TEST simulation only. Production candidate ranking,
  scheduler, escrow and settlement belong to later MAGNA sprints.
