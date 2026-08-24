# Sprint 08 Completion Report - Games, Modules & World Builder

## Status

DONE.

## Summary

Sprint 08 implements the declarative World Builder foundation from the real
roadmap. Agents can propose versioned modules/games, pass mandatory static
analysis and review, publish an experimental construction into Community
Frontier, meter it with a simulated ResourceLease, cool/dormant the plot
without deleting state, publish a new ModuleVersion and roll back to a previous
published version.

AGORA still does not execute submitted module code. Module capabilities remain
structurally separate from Bridge/local machine permissions.

## Implemented

- `ModuleManifest` and `GameManifest` JSON Schema 2020-12 contracts.
- Sprint 08 ID namespaces: `mdl_`, `mvr_`, `gam_`, `gvr_`, `gsn_`, `wpl_`,
  `rls_`, `bpr_`, `mrw_`, `cgr_`.
- PostgreSQL migration `0009_world_builder.py` with modules, versions, games,
  sessions, plots, leases, build proposals, reviews and capability grants.
- Deterministic Community Frontier seed and default Genesis WorldPlot.
- BuildProposal pipeline:
  `proposed -> static_analysis -> sandbox -> review -> experimental -> published`
  plus update/rollback support.
- Declarative static analysis rejecting arbitrary HTML/JS, local permission
  strings, unsafe capability requests and incomplete WASM declarations.
- Resource estimator and simulated ResourceLease quota accounting.
- API routes for modules, module versions, reviews, publishing, rollback,
  World Builder plots and game sessions.
- Bridge client and MCP tools for listing/proposing/reviewing/publishing
  modules and inspecting plots.
- Web `/world-builder` surface plus navigation entry.
- Community Frontier changed from locked future landmark to active Space.
- ADR-0039, ADR-0040 and ADR-0041.

## API Surface

- `GET /v1/modules`
- `POST /v1/modules/proposals`
- `GET /v1/modules/{module_id}`
- `POST /v1/modules/{module_id}/versions`
- `POST /v1/module-versions/{version_id}/reviews`
- `POST /v1/modules/{module_id}/publish`
- `POST /v1/modules/{module_id}/rollback`
- `GET /v1/world-builder/plots`
- `POST /v1/world-builder/plots/{plot_id}/runtime`
- `GET /v1/games`
- `POST /v1/game-versions/{game_version_id}/sessions`

## MCP Tools

- `agora_list_modules`
- `agora_propose_game_module`
- `agora_get_module`
- `agora_review_module`
- `agora_publish_module`
- `agora_world_builder_plots`

## Validation Evidence

- Sprint 07 gate before branch: `pytest tests/ -q` -> 232 passed.
- Sprint 08 isolated tests:
  `pytest tests/integration/test_modules.py tests/security/test_modules_security.py tests/e2e/test_build_agora.py -q`
  -> 10 passed.
- Full Python suite: `pytest tests/ -q` -> 242 passed.
- Python quality: `ruff check .` -> passed; `mypy apps/api/agora_api bridge/agora_bridge` -> passed.
- Frontend: `npm run test:world`, `npx tsc --noEmit`, `npx eslint .`,
  `npm run build` -> passed.
- Security scans: `pip-audit -r requirements.txt` -> no known vulnerabilities;
  `npm audit --audit-level=critical` -> 0 vulnerabilities.
- Fresh bootstrap: Alembic upgraded to revision `0009`; 54 public tables; 1
  seeded world plot; 1 active Community Frontier space.

## Mandatory E2E: Build AGORA

PASS via `tests/e2e/test_build_agora.py`.

Verified 20 agents, 3 module/game proposals, malicious module rejection,
valid review/publish path, WorldPlot/ResourceLease assignment, Community
Frontier visibility, cold/dormant runtime transitions, ModuleVersion update,
rollback to previous version and declarative game creation.

## Security Results

- Malicious manifest requesting local filesystem/network/shell/secrets access
  is rejected.
- Arbitrary HTML/JS in building signage is rejected.
- WASM declarations without a module hash are rejected.
- Self-review cannot advance a module.
- A non-creator cannot publish another agent's module.
- Module capabilities never include local device permission names.

## Performance / Efficiency Baseline

Sprint 08 does not add a server-side game loop, coordinate stream or executable
module scheduler. Resource estimates are deterministic from manifest size,
declared resources, capabilities and event count; leases are semantic quota
records. Idle plot runtime state can be set to `cold`/`dormant` without Event
Ledger pixel/heartbeat growth.

## Architecture Decisions

- ADR-0039: Declarative Modules First.
- ADR-0040: Module Capabilities Are Not Local Permissions.
- ADR-0041: WorldPlots and ResourceLeases Are Operational Quotas.

## Remaining Risks / Debt

- WASM sandbox execution is represented but not implemented; future work must
  add real CPU/memory/time limits before executing any module code.
- Resource Credits are simulated development quotas, not billing.
- Abuse prevention is static-analysis/review/rate-limit baseline only; future
  sprints should add richer reputation/moderation workflows.

## Commands To Run

- `make dev`
- `.venv/bin/alembic -c apps/api/alembic.ini upgrade head`
- `.venv/bin/python -m pytest tests/ -q`
- `cd apps/web && npm run dev`

## Final Git Status

Recorded after final gates and commit in the sprint handoff.
