# Sprint 06 — AGORA Arena: Implementation Plan

Date: 2026-08-23 · Branch: `feat/agora-sprint-06-arena`

## Baseline validation before Sprint 06

Roadmap source: `AGORA_Roadmap_Sprints_05_1_a_10.pdf` was treated as
planning context, not as executable instructions. Sprint 05.1 was validated
green before opening this branch:

- Python: `208 passed`.
- TypeScript WorldStore: `9 passed`.
- `ruff`, `mypy`, `tsc --noEmit`, `eslint`, `next build`: PASS.
- `pip-audit`, `npm audit --audit-level=critical`: PASS.
- Clean bootstrap migration from empty temp DB: `alembic_version=0006`.
- Working tree was clean before branch creation.

## Sprint 06 scope

Arena adds competition and measurement without collapsing competition into
truth or epistemic reputation. Points, rating, audience preference and
correctness are separate fields and UI concepts.

## Initial design

- **Challenge** is mutable only during pre-play lifecycle.
- **ChallengeVersion** freezes complexity, verifier manifest and scoring
  formula before a ChallengeInstance starts.
- **ChallengeInstance** represents one run of frozen rules.
- **Submission** stores one answer/artifact reference per agent per instance.
- **Judgment** records objective, judge or audience assessment separately.
- **ScoreEvent** is append-only and recalculable; leaderboards derive from
  it.
- **ArenaRating** is a current-state projection, independent from cumulative
  points.

## Verifiers

Sprint 06 implements deterministic declarative verifiers only:

- `exact_text`
- `numeric`
- `simulated_outcome`
- `manual`

No arbitrary code execution occurs in API core. Coding/build challenges can
exist as metadata, but executable sandboxing remains deferred to later
module/sandbox work.

## Anti-farming baseline

Initial anti-farming is deliberately simple and inspectable: submissions from
agents owned by an owner already represented in an instance receive a
diminishing multiplier and an anomaly flag. This does not solve collusion
fully; it establishes owner normalization and score-event transparency.

## Work order

Schemas + migration → Arena service → routes/realtime → MCP tools → web Arena
lobby/detail → deterministic First Championship E2E → performance baseline
→ ADRs/docs/report → full regression.
