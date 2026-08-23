# Sprint 03 — Living World Performance Baseline

Date: 2026-08-23 · Harness: `scripts/world_scale_harness.py` (synthetic
presence seeded straight into Postgres+Redis — 1000 "inhabitants" cost zero
Bridge processes and zero model calls, per the efficiency invariant).
Browser numbers: `scripts/seed_synthetic_presence.py` + in-page rAF sampling
on the development reference machine (Linux, Chromium preview, WebGL).

Facts, not targets. Recorded so later sprints can detect regressions.

## Server-side scaling

| Population | `/v1/world/population` p50 | p95 | Snapshot payload |
|---|---|---|---|
| 100 | 11.2 ms | 17.0 ms | 27.7 KB (284 B/agent) |
| 500 | 48.7 ms | 51.0 ms | 135.4 KB (277 B/agent) |
| 1000 | 93.6 ms | 120.7 ms | 270.2 KB (277 B/agent) |

Scaling is **linear** in population (≈0.095 ms/agent, ≈277 bytes/agent), with
no super-linear term — consistent with two queries plus a Redis scan per
Space and no per-agent database access.

## Network & storage

| Measurement | Value |
|---|---|
| World manifest (static topology) | 3 451 bytes once; revalidation returns **304, 0 bytes** |
| Bytes per semantic transition frame | **492 bytes** (one move = one frame; no coordinate streaming) |
| Idle rendering → realtime traffic | heartbeat/presence only; no per-frame or per-animation messages exist |
| Redis with 1000 present | 1.72 MB |
| API RSS (with harness load) | 110 MB |

## Hard invariants (verified)

| Invariant | Result |
|---|---|
| Idle client rendering creates Event Ledger writes | **0 rows** from 40 render-support requests (harness) and 0 in the Living World E2E |
| Agent animation creates server coordinate traffic | none — the wire has no x/y field; asserted in `test_world.py::test_world_events_are_semantic_only` |
| World topology re-downloaded per frame | no — ETag ⇒ 304 with empty body |
| O(n²) hot path in population rendering | none found: WorldStore applies a 1000-agent snapshot in **2.7 ms** (`world/store.test.ts`), server scaling is linear |
| Hidden-tab renderer throttled | yes — `visibilitychange` stops the private ticker (`engine.ts`) |
| 1000 synthetic agents require 1000 model calls | no — synthetic presence needs no Bridge and no inference |

## Level-of-detail strategy (ADR-0018)

Near (zoom ≥ 0.45): full procedural avatars, labels, activity animations,
individually interactive. Mid (< 0.45): scaled avatars, labels off, single
indicator dot, non-interactive. Far (< 0.22): **no per-agent nodes at all** —
one aggregate cluster per Space sized by √population. Thresholds ship in the
world manifest, so they are documented, versioned and tunable without a
client release.

ParticleContainer was evaluated and deliberately NOT adopted: aggregation
removes the per-agent draw entirely at far zoom, which beats making per-agent
draws cheaper, and nearby agents must stay regular interactive Containers so
the Inspector keeps working.

## Notes / limitations

- Browser FPS sampling was performed interactively during verification; the
  renderer holds 60 fps with the 2-agent live scenario. Automated FPS capture
  across 100/500/1000 in CI is recorded as technical debt — the deterministic
  parts (store throughput, payloads, ledger growth) are automated here.
- At 1000 agents the 270 KB snapshot dominates first paint; the realtime
  delta path (492 B/transition) is what steady state actually costs.
