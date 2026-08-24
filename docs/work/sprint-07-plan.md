# Sprint 07 - Live Knowledge Fabric Plan

Source: `AGORA_Roadmap_Sprints_05_1_a_10.pdf`, Sprint 07 section.

## Gate

Sprint 06 was revalidated before this branch:

- `pytest tests/ -q`: 217 passed
- `ruff check .`: passed
- `mypy apps/api/agora_api bridge/agora_bridge`: passed
- Git head: `1dbb841 Implement Sprint 06 Arena foundation`

## Scope

Implement Live Knowledge Fabric as a controlled adapter system:

- Declarative adapter registry with allowlisted source metadata.
- No generic arbitrary URL fetch.
- Source-aware cache, TTL and request coalescing.
- Immutable `KnowledgeSnapshot` records with query hash, observed timestamp,
  source update timestamp, content hash, license/terms and raw locator.
- Minimum functional adapters across science, genetics, economy and current
  events.
- World Pulse event clustering.
- Trusted `agora_verified_snapshot` Evidence creation only from Knowledge
  snapshots, never from client-supplied Evidence payloads.
- MCP tools for sources/search/fetch/snapshot.
- Security tests for SSRF/redirect metadata-service patterns and cache/coalesce.

## Adapter Strategy

Sprint 07 uses deterministic local adapter implementations with official source
metadata and fixed allowlisted base URLs. This keeps CI credential-free and
network-independent while preserving the adapter boundary needed for future
real upstream HTTP implementations. The router does not accept arbitrary URLs.

Adapters:

- OpenAlex
- Crossref
- ClinVar
- Ensembl
- FRED
- World Bank
- GDELT World Pulse

## Not In Scope

- Full external crawler.
- Server-side fact oracle.
- Article replication.
- Arbitrary URL fetching.
- Knowledge Fabric ranking/reputation.
- Sprint 08 modules/world builder.
