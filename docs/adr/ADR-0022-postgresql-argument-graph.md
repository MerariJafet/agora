# ADR-0022: PostgreSQL Argument Graph First

Status: Accepted · Date: 2026-08-23

## Decision
The argument graph (Claims as nodes, ClaimRelations as edges) lives in
PostgreSQL, queried through bounded neighborhood expansion
(`graph_service.get_neighborhood`) — no graph database (Neo4j or otherwise)
was introduced.

Bounds, all explicit and enforced in code:
- `MAX_DEPTH = 2` — the API rejects `depth` outside 1-2.
- `MAX_RELATIONS_PER_LEVEL = 200` — each BFS level fetches at most this many
  relation rows.
- `MAX_NODES = 300` — traversal stops once this many distinct claims are
  touched; the response sets `"truncated": true` so a client can tell.

Depth-1 is two indexed queries (relations touching the root, by source or
target). Depth-2 repeats that once more for the depth-1 frontier. There is no
recursive CTE, and the full graph is never transmitted by default.

## Rationale
At Sprint 04 scale (validated up to 1000 claims / 2000 relations, see
sprint-04-baseline.md: depth-2 queries in ~3-4 ms p95) a graph database adds
operational surface — another datastore to run, back up and secure — for a
problem two indexed lookups already solve. "Do not introduce a graph
database without demonstrated need" (explicit sprint constraint).

## Consequences
- If a future sprint needs deep multi-hop traversal (mission dependency
  graphs, citation chains spanning thousands of hops), that is the trigger
  to revisit this decision — not before.
- Every claim detail/list/graph endpoint stays a bounded, explainable query
  plan reviewable in a normal Postgres EXPLAIN, not an opaque graph traversal.
