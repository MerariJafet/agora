# ADR-0041: WorldPlots and ResourceLeases Are Operational Quotas

## Status

Accepted.

## Context

The Community Frontier needs persistent locations and resource accountability,
but AGORA must not introduce financialized land, NFTs or artificial scarcity.

## Decision

`WorldPlot` is a persistent semantic location with runtime state
`hot/warm/cold/dormant`. `ResourceLease` records simulated Resource Credits and
estimated storage/events/bandwidth/sandbox budget for a published module.

Plots are not financial ownership. Leases are auditable operational quotas in
Sprint 08 development mode.

## Consequences

- Empty or idle areas can become cold/dormant without losing persistent state.
- World rendering can show buildings without server-side animation state.
- Future billing/metering can attach to the lease abstraction without changing
  module identity.
