# Sprint 08 - Games, Modules & World Builder Plan

Source: `AGORA_Roadmap_Sprints_05_1_a_10.pdf`, Sprint 08 section.

## Gate

Sprint 07 was revalidated before opening this branch:

- `pytest tests/ -q`: 232 passed
- `ruff check .`: passed
- `mypy apps/api/agora_api bridge/agora_bridge`: passed

## Scope

Implement a declarative World Builder foundation:

- Versioned `ModuleManifest` and `GameManifest` schemas.
- BuildProposal pipeline:
  `proposed -> static_analysis -> sandbox -> review -> experimental -> published -> deprecated/archived`.
- Default-deny capability model. Module capabilities are platform/module
  capabilities, never local device permissions.
- Declarative runtime first; no arbitrary JS/HTML in privileged origin.
- Optional WASM is represented but not executed in API core.
- Resource estimator and simulated Resource Credits/quota model.
- WorldPlot and ResourceLease as persistent location/quota, not financial
  ownership.
- Hot/warm/cold/dormant plot runtime states.
- Community Frontier active in the world manifest.
- Agent-created game proposal through API/MCP.
- Module review and version/rollback support.

## Not In Scope

- Arbitrary community JavaScript execution.
- Real billing, crypto/NFTs or artificial land scarcity.
- Kubernetes-style scheduler or new microservice.
- Sprint 09 civic agents/replay.
