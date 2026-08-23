# Sprint 05.1 — Missions & Artifacts Completion Gate: Plan

## Baseline audit (S5.1-T01)

Reporting ambiguity resolved: the Sprint 05 report's "202/202 tests passing"
referred **only** to the Python `pytest` suite. It did not separately state
the TypeScript suite, which is unchanged from Sprint 04 at **9 tests**
(`apps/web/world/store.test.ts`, run via `npm run test:world`). No frontend
work happened in the Sprint 05 core pass, so the TypeScript count could not
have changed.

| Suite | Sprint 04 baseline | Sprint 05 core (start of 05.1) |
|---|---|---|
| Python (pytest) | 172 | 202 (172 + 30 new) |
| TypeScript (node --test) | 9 | 9 (unchanged) |
| Browser/E2E (subset of the Python count, `-m e2e`) | — | 9 |
| **Combined** | 181 | 211 |

## Sprint 05 P0 task → status map

| Task | Status | Note |
|---|---|---|
| S5-T01..T20 (Mission/Artifact core) | Implemented | Accepted; not reimplemented this pass |
| S5-T09 A2A MissionTask adapter | **Was missing → implemented in 05.1** | `mission_a2a_adapter.py` |
| S5-T21 MCP tools | Implemented | 13 tools, unchanged |
| S5-T22 Mission realtime events | **Partially broken → fixed in 05.1** | Events existed but were published to an unscoped `scope="global"` that nothing subscribes to; rescoped to `mission_id`/`hosting_space_id`/`artifact_id` |
| S5-T23 Mission Board UI | **Was missing → implemented in 05.1** | `apps/web/app/missions/` |
| S5-T24 Living World Mission indicator | Deferred (P1) — see below | |
| S5-T25 Artifact security suite | Implemented | path traversal, symlink, secrets, oversized, tamper |
| S5-T26 Mission concurrency/failure tests | Partially implemented | claim races, stale-attempt rejection; see 05.1 additions |
| S5-T27 Efficiency baseline | **Was missing → implemented in 05.1** | `docs/work/sprint-05-1-baseline.md` |
| S5-T29 Audit/privacy review | **Was missing → implemented in 05.1** | `docs/work/sprint-05-privacy-audit.md` |
| S5-T30 Docs/ADRs | **Partially missing → completed in 05.1** | ADR-0029/30/31 added; protocol/architecture/threat-model synced |
| S5-T31 Full regression | Re-run in 05.1 with lint/type/audit tooling added | |

## Standards re-verification

- **A2A**: `a2a-sdk` pinned at 1.1.2 (protocol 1.0.x canonical types). Not
  upgraded — the gate's `never` list forbids implementing an MCP Tasks
  runtime the pinned SDK doesn't support, and re-checking `pip index
  versions a2a-sdk` during this pass showed no 1.0.x-breaking change that
  would require touching the pin. `MissionTask` remains an AGORA social
  object; the A2A `Task` created for delegation is its cross-agent
  interoperability transport only (ADR-0026, extended by ADR-0029).
- **MCP**: `mcp` pinned at 2.0.0. The installed SDK does not expose an
  official Tasks runtime for the 2026-07-28 revision — confirmed by
  inspecting the installed package's public API
  (`python -c "import mcp; ..."`, no `Task`/`TaskState` types exported
  alongside the existing `Tool`/`Resource` surface). Per the gate's
  explicit instruction, MCP Tasks were **not** implemented; the existing
  stdio tool surface (now 36 tools total across Sprints 02-05.1) is
  unchanged in shape.

## Order of work for 05.1

1. Baseline audit (this document).
2. A2A MissionTask adapter + idempotency/stale-attempt tests (S5.1-T02..T05).
3. Mission realtime scoping fix + verification test (S5.1-T06).
4. Mission Board UI + accessibility (S5.1-T07/T08).
5. Living World indicator or justified deferral (S5.1-T09).
6. Efficiency baseline dataset + measurements (S5.1-T10..T12).
7. Privacy/audit review (S5.1-T13).
8. Docs sync + ADR-0029/30/31 (S5.1-T14/T15).
9. Mandatory E2E restoration with real cross-Bridge delegation + browser
   verification (S5.1-T16/T17).
10. Full regression, lint/type/security tooling, fresh bootstrap (S5.1-T18).

## Living World Mission indicator (S5.1-T09) — deferral rationale

Deferred to a follow-up pass. The Mission Board (S5.1-T07) already gives
full semantic visibility into active/completed Missions; the incremental
value of a world-map badge is presentation polish on top of data the UI
already exposes, not new capability. None of the gate's actual
`blocking_gaps` or `acceptance_invariants` name the World indicator as a
condition for E2E or completion correctness — it is listed as its own P1
item precisely because it is separable. Concrete follow-up: a `<20 line`
PixiJS layer reading the same `mission` realtime scope already wired up in
S5.1-T06, rendering a small badge on `hosting_space_id`'s tile.
