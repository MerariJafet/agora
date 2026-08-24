# ADR-0038: Source-Defined Freshness

## Status

Accepted.

## Context

Live Knowledge Fabric should not label weekly, daily or historical data as
realtime merely because AGORA fetched or cached it recently.

## Decision

Every `KnowledgeSource` and `KnowledgeSnapshot` carries a freshness contract:
`REALTIME`, `NEAR_REALTIME`, `HOURLY`, `DAILY`, `WEEKLY`, `IRREGULAR` or
`HISTORICAL`. UI and MCP surfaces expose this value. World Pulse clusters
inherit source freshness and never imply truth.

## Consequences

- Humans and agents can distinguish source cadence from AGORA cache time.
- Forecasting, Arena and Missions can pin data available at a time without
  claiming it was realtime.
- Future source adapters must document freshness explicitly before use.
