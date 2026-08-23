# Sprint 04 — Social Intelligence Performance Baseline

Date: 2026-08-23 · Harness: `scripts/epistemic_scale_harness.py` — seeds
1000 Claims, ~2000 ClaimRelations, 1500 Evidence objects, 100 Debates and
5000 AudienceAssessments directly into Postgres (no crypto, no Bridge
processes, no model calls) then benchmarks the read paths a browser or
agent actually exercises.

Facts, not targets. Recorded so later sprints can detect regressions.

## Read-path latency (warm, 30 samples each)

| Operation | p50 | p95 |
|---|---|---|
| Claim list (Space, 50/page) | 1.7 ms | 2.0 ms |
| Claim detail | 1.1 ms | 1.3 ms |
| Argument-graph neighborhood, depth=1 | 2.3 ms | 3.3 ms |
| Argument-graph neighborhood, depth=2 | 3.4 ms | 4.3 ms |
| Audience assessment-summary (pure SQL aggregation) | 3.3 ms | 4.2 ms |

## Scale facts

- Depth-2 neighborhood around a representative claim in the 1000-claim
  corpus: 5 claims, 8 relations, 5 093 bytes — comfortably inside the
  browser's bounded SVG rendering budget; `truncated: false` (well under the
  300-node cap).
- PostgreSQL database size after seeding: 20 MB.
- API RSS during the benchmark run: 105 MB (in line with Sprint 01-03 baselines).
- Seeding 1000 claims + 2000 relations + 1500 evidence + 100 debates + 5000
  assessments: 0.8 s (bulk `session.add` + one flush per FK-dependent stage).

## Realtime propagation

Claim/Evidence/Relation/Debate/Assessment creation each publish one bounded
frame to the owning Space via the existing NATS-backed gateway (Sprint 02/03
infrastructure, unchanged); no new fanout mechanism was introduced.
Assessment updates publish the recomputed AGGREGATE, never individual raw
votes, keeping fanout size independent of assessor count.

## Efficiency invariants verified

- No N+1: claim list, evidence attachment list and relation list are each a
  single indexed query (or a two-way join for evidence-with-role).
- Graph neighborhood is two-to-four bounded queries total regardless of
  corpus size (frontier expansion capped at `MAX_RELATIONS_PER_LEVEL=200`
  and `MAX_NODES=300`) — never a recursive CTE, never a full-graph scan.
- Audience aggregation uses `AVG`/`COUNT`/`GROUP BY` in Postgres; no
  assessment row is ever loaded into Python for aggregation.
- No LLM inference anywhere in the epistemic domain or its tests.
