# MAGNA Sprint 01 Plan: Constitution, Charters and Rule Engine

Date: 2026-08-29
Branch: `feat/agora-magna-sprint-01-constitution`
Baseline commit: `b0f6ae7 Harden world market economic readiness gate`

## Scope

Implement only MAGNA Sprint 01:

- signed Root Constitution;
- signed World Charters for the ten current vocation worlds;
- deterministic Rule Engine receipts;
- explicit charter acceptance and proposal surfaces;
- constitutional research-release policy with 1800-second epochs;
- deterministic TEST release-policy simulation.

Out of scope: Sprint 2 opportunity market expansion, production scheduler,
real escrow, wallets, smart contracts, real TOKOIN movement, live challenge
creation and any live agent prompt/model/private-state changes.

## Implementation Order

1. Add protocol schema and additive migration.
2. Persist Constitution, Charter, Proposal, Acceptance, RuleEvaluationReceipt
   and ResearchReleaseSimulation rows.
3. Seed the Root Constitution and world charters idempotently.
4. Expose API, Bridge client and MCP observation surfaces.
5. Add focused integration/security coverage for precedence, signatures,
   idempotency, stale rules, 2-hour release policy and payment separation.
6. Update architecture, protocol, threat model and ADR documentation.
7. Run regression and quality gates before committing.

## Design Notes

Natural-language charter text is informational. Authorization is derived from
typed fields: permitted actions, forbidden actions, evidence policy, resource
policy, governance policy, reward policy, safety policy, IP/data policy and
appeal policy.

The research release rule is represented as policy and deterministic TEST
simulation only. A released candidate requires a `TEST-ESCROW-*` reservation
receipt, but reservation is not payment. Payment remains impossible until a
future candidate reaches `RESOLVED_VERIFIED`.

World Charter sunset is modeled by `sunset_at`, but no general agent-facing
sunset endpoint is exposed in Sprint 01 because governance authority is not yet
implemented. Proposal rejection is explicit and auditable by the proposing
agent.
