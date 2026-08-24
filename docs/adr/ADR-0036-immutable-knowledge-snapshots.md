# ADR-0036: Immutable Knowledge Snapshots

## Status

Accepted.

## Context

"Live" source data can change. AGORA must let Debates, Missions, Claims,
Artifacts and Arena Challenges pin what was observable at a time without
rewriting history when a source later updates.

## Decision

`KnowledgeSnapshot` is an immutable observation record containing query hash,
normalized query, observed timestamp, source update timestamp when available,
content hash, raw locator, license terms, freshness contract and bounded result
metadata.

Refreshing a source creates a new snapshot. Existing Evidence, Mission and
Debate references remain pinned to the original snapshot id/content hash.

## Consequences

- AGORA can represent source drift honestly.
- Reproducibility is possible without pretending old data was current.
- Storage grows with snapshots, so TTL/cache metrics and future retention policy
  matter, but canonical snapshot history is not silently rewritten.
