# Sprint 07 - Live Knowledge Fabric Completion Report

## Status

DONE.

## Executive Summary

Sprint 07 adds Live Knowledge Fabric without turning AGORA into a generic
crawler or central truth oracle. AGORA now has an allowlisted KnowledgeSource
registry, source-aware cache/coalescing, immutable KnowledgeSnapshots,
World Pulse clustering, MCP tools and a trusted path for materializing
KnowledgeSnapshots as `agora_verified_snapshot` Evidence.

World Pulse is active in the Genesis World. Freshness is source-defined and
visible. Verified snapshot provenance means adapter provenance, not factual
truth.

## Sprint 06 Validation Before Start

- Branch started from `1dbb841 Implement Sprint 06 Arena foundation`.
- `pytest tests/ -q`: 217 passed.
- `ruff check .`: passed.
- `mypy apps/api/agora_api bridge/agora_bridge`: passed.

## Implemented

- `knowledge.schema.json` for QueryRequest and SnapshotEvidenceRequest.
- ID namespaces: `kso_`, `ksn_`, `wpe_`.
- Migration `0008_knowledge_fabric.py` with:
  - `knowledge_sources`
  - `knowledge_snapshots`
  - `world_pulse_events`
  - `world_pulse_sources`
  - deterministic World Pulse Space seed
  - 8 allowlisted sources.
- Deterministic adapter boundary for OpenAlex, Crossref, ClinVar, Ensembl,
  FRED, World Bank, GDELT World Pulse and NASA public data.
- Cache/coalescing by source/query/as_of.
- Immutable snapshot creation with content hash, observed/source timestamps,
  license terms, freshness contract and raw locator.
- World Pulse clustering from multiple allowed sources.
- Trusted snapshot-to-Evidence route.
- Bridge client and MCP tools for Knowledge.
- Web World Pulse page and nav entry.
- Architecture/protocol/threat model/ADRs updated.

## API Endpoints

- `GET /v1/knowledge/sources`
- `POST /v1/knowledge/search`
- `GET /v1/knowledge/snapshots/{snapshot_id}`
- `POST /v1/knowledge/snapshots/{snapshot_id}/evidence`
- `GET /v1/world-pulse/events`

## MCP Tools

- `agora_knowledge_sources`
- `agora_knowledge_search`
- `agora_knowledge_fetch`
- `agora_knowledge_snapshot`
- `agora_world_pulse`

## One Event, Many Minds

PASS. Automated in `tests/e2e/test_one_event_many_minds.py`.

Verified:

- 20 synthetic agents issue the same World Pulse query.
- Cache/coalescing returns one shared snapshot for the same source/query.
- A second allowed source clusters into one World Pulse event.
- Claim/Evidence uses `agora_verified_snapshot` from a KnowledgeSnapshot.
- Debate and Mission reference the pinned Claim/snapshot context.
- Refresh creates a new snapshot without rewriting old Evidence.
- SSRF-style metadata-service query is rejected.

## Security Results

- URL/internal locator Knowledge queries rejected.
- Unknown `source_id` cannot become generic fetch.
- Client-created Evidence still cannot self-certify `agora_verified_snapshot`.
- Snapshot evidence requires a real existing snapshot.
- World Pulse does not expose truth or reputation scoring.
- Adapters return bounded metadata/excerpts, not full articles.

## Regression Results

- Sprint 07 isolated tests: `15 passed`.
- Python full suite: `232 passed in 68.24s`.
- Frontend world tests: `9 passed`.
- Ruff: `All checks passed!`.
- Mypy: `Success: no issues found in 72 source files`.
- TypeScript strict check: passed.
- ESLint: passed.
- Next build: passed.
- pip-audit: `No known vulnerabilities found`.
- npm audit critical: `found 0 vulnerabilities`.
- Fresh migration bootstrap: reached `0008`, created 44 public tables, seeded
  8 KnowledgeSources and 1 World Pulse Space.

## Performance / Cache Baseline

The E2E and integration tests verify 20 duplicate same-source queries coalesce
to one snapshot/upstream adapter call. `knowledge_sources` tracks
`upstream_call_count` and `cache_hit_count` per source so hit ratio can be
observed without logging private prompt/content.

## Architecture Decisions

- ADR-0035: Controlled Knowledge Adapter Registry.
- ADR-0036: Immutable Knowledge Snapshots.
- ADR-0037: Verified Evidence From Knowledge Boundary.
- ADR-0038: Source-Defined Freshness.

## Technical Debt

- Sprint 07 adapters are deterministic local implementations. Real upstream
  HTTP adapters should be added behind the same registry/policy boundary with
  redirect, timeout, decompression and content-size enforcement.
- Cache expiration exists via TTL; no operator UI exists yet for manual source
  circuit-breaker reset.
- World Pulse clustering uses deterministic query/event keys, not a full
  semantic clustering engine.

## Recommended Sprint 08 Preconditions

- Preserve Knowledge adapter boundary before any module/world-builder feature
  consumes public source data.
- Do not allow modules to introduce arbitrary URL fetching or bypass snapshot
  provenance.
- Decide whether real upstream adapters should be enabled in dev only through
  fixture-backed tests or optional operator configuration.
