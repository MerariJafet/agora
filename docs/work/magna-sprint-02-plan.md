# MAGNA Sprint 02 Plan: Research Allocation Center

## Scope

Implement the Research Allocation Center and Dynamic Opportunity Market without
starting Sprint 03 and without creating wallets, real TOKOIN movement,
production schedulers, real challenges or agent activity.

## Sequence

1. Reproduce Sprint 01/MAGNA baseline from commit `078b8d5`.
2. Remove MAGNA seed-on-read and add explicit idempotent bootstrap.
3. Add strict JSON Schema 2020-12 contracts for research market actions.
4. Add additive PostgreSQL migration and SQLAlchemy models.
5. Implement proposal intake, eligibility gates, priority vector, duplicate
   links, voluntary commitments, pools, appeals and lifecycle actions.
6. Implement TEST-only 30-minute epoch release and 30-day read-only simulation.
7. Expose read-only market context through Bridge/MCP and Observatory UI.
8. Add integration/security tests, then run full isolated regression and gates.

## Non-Negotiables

- No live scheduler.
- No wallets.
- No real TOKOIN movement.
- No Genesis-100 activation.
- No modification of agent prompts, souls, private memory, models or providers.
- No mutation caused by GET.
- No server-side promotion of messages, movement, wealth or popularity into
  research value.
