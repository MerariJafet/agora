# Sprint 05.1 — Missions & Artifacts Performance Baseline

Date: 2026-08-23 · Harness: `scripts/mission_scale_harness.py` — seeds 250
Missions, 5000 MissionTasks, 6999 dependency edges, 1000 Artifacts, 2000
ArtifactVersions and 3000 ArtifactReviews directly into Postgres (no
crypto, no Bridge processes, no model calls), then benchmarks the read/write
paths a coordinator or the Mission Board actually exercises, plus streaming
upload/download throughput at 1/10/100 MB.

Facts, not targets. Recorded so later sprints can detect regressions.

## Read-path latency (warm, 30 samples each)

| Operation | p50 | p95 |
|---|---|---|
| Mission list (50/page) | 1.8 ms | 2.4 ms |
| Mission detail | 1.5 ms | 1.8 ms |
| Mission task DAG (tasks list) | 1.6 ms | 1.7 ms |
| Artifact detail (with versions) | 1.5 ms | 1.7 ms |

## Write-path / transactional latency (30 samples each, real registered agent)

| Operation | p50 | p95 |
|---|---|---|
| Transactional task claim (`SELECT ... FOR UPDATE`) | 4.6 ms | 6.7 ms |
| Lease renewal | 2.9 ms | 4.0 ms |
| Completion evaluation (full accept + policy eval, 10 samples) | 4.8 ms | 5.8 ms |

## Streaming upload/download

| Size | Upload time | Upload throughput | API RSS during | Download time | Download throughput |
|---|---|---|---|---|---|
| 1 MB | 12 ms | 80.1 MB/s | 111 MB | 5 ms | 183.8 MB/s |
| 10 MB | 34 ms | 295.9 MB/s | 115 MB | 15 ms | 647.0 MB/s |
| 100 MB | 585 ms | 170.8 MB/s | 113 MB | 126 ms | 792.0 MB/s |

**Bounded-memory claim verified**: API RSS stays flat (111-115 MB) across
the 1/10/100 MB uploads — a 100 MB upload does **not** require ~100 MB of
additional API process memory, because `LocalArtifactStore.put_stream`
hashes and writes each 1 MB chunk to the quarantine temp file as it arrives
(`os.fdopen(...).write(chunk)` inside the async-for loop) rather than
buffering the full body first.

## Scale facts

- Seeding 250 missions + 5000 tasks + 6999 edges + 1000 artifacts + 2000
  versions + 3000 reviews: 1.2 s.
- PostgreSQL database size after seeding (including the 2000 synthetic
  blob-backed versions' rows, not their bytes — those live in the
  filesystem ArtifactStore): 21 MB.
- Content-addressed dedup verified directly: publishing the same 1 MB of
  bytes twice under different declared filenames yields the same
  `content_hash` and the same underlying blob (`LocalArtifactStore`
  short-circuits to the existing file once size matches).
- Final API RSS after the whole run (seeding + all benchmarks + three
  upload sizes + dedup check): 115 MB — in line with Sprint 01-04 baselines.

## Efficiency invariants verified

- No N+1: Mission list/detail, MissionTask DAG listing, and Artifact detail
  (with its versions) are each backed by a single indexed query (or one
  join for versions-by-artifact).
- The task dependency DAG has no recursive CTE and no full-graph scan: task
  readiness is recomputed by one bounded query per pending task
  (`_refresh_readiness`), and cycle rejection (`_would_create_cycle`) is a
  capped-iteration BFS (≤200 hops) that is structurally unreachable in
  normal use since new tasks can only reference already-existing ones.
- Transactional claim/assign is exactly one row-locked `SELECT ... FOR
  UPDATE` plus one `UPDATE` — no polling loop, no second datastore.
- No LLM inference anywhere in the Mission/Artifact domain or its tests.

## Realtime propagation

Mission/MissionTask/Artifact/Review events each publish one bounded frame,
scoped by `mission_id` (and the hosting Space, when set) or `artifact_id` —
see the S5.1-T06 fix in `routes/missions.py`/`routes/artifacts.py`. Lease
renewal deliberately publishes nothing (verified in
`tests/e2e/test_mission_realtime.py`).
