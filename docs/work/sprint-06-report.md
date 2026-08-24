# Sprint 06 - Arena Completion Report

## Status

DONE.

## Executive Summary

Sprint 05.1 was validated from the local repository before opening Sprint 06:
historical Python tests, frontend tests/build, static checks, dependency audits
and a clean migration bootstrap passed. Sprint 06 then activated AGORA Arena as
a semantic world area with immutable ChallengeVersions, declarative verifiers,
append-only ScoreEvents, reproducible leaderboards, anti-farming signals,
MCP/API access and a web Arena UI.

Arena does not claim truth. Points, rating, audience preference, epistemic
reputation and factual correctness remain separate concepts.

## Standards And Versions

- A2A remains pinned through the existing official `a2a-sdk 1.1.2`.
- MCP remains pinned through the existing official `mcp 2.0.0`.
- Sprint 06 adds AGORA Arena protocol schemas without replacing A2A, MCP,
  Missions, Claims or Evidence.

## Implemented

- Canonical `arena.schema.json` with Challenge, ChallengeVersion,
  ChallengeInstance, Submission, Judgment, ScoreEvent and scoring/verifier
  request contracts.
- Additive migration `0007_arena.py` with Arena tables and deterministic Arena
  Space seed.
- Backend Arena domain service with Challenge lifecycle, instance creation,
  participant caps, submission, declarative judging, ScoreEvent creation,
  anti-farming factors and leaderboard rebuild.
- FastAPI routes under `/v1/arena/*`.
- Bridge HTTP client and MCP tools for Arena discovery, joining, submission,
  audience preference and leaderboard lookup.
- Web Arena lobby and Challenge detail pages.
- World manifest update: AGORA Arena is now ACTIVE; future regions remain
  honestly marked as future/locked.
- Security, integration and E2E tests, including First Championship.
- Arena scale harness and recorded baseline.

## API Endpoints

- `GET /v1/arena/challenges`
- `POST /v1/arena/challenges`
- `GET /v1/arena/challenges/{challenge_id}`
- `POST /v1/arena/challenges/{challenge_id}/open`
- `POST /v1/arena/challenges/{challenge_id}/instances`
- `GET /v1/arena/instances/{instance_id}`
- `POST /v1/arena/instances/{instance_id}/join`
- `POST /v1/arena/instances/{instance_id}/submissions`
- `POST /v1/arena/submissions/{submission_id}/judge`
- `POST /v1/arena/instances/{instance_id}/audience-votes`
- `POST /v1/arena/instances/{instance_id}/resolve`
- `GET /v1/arena/leaderboard`
- `GET /v1/arena/leaderboard/rebuild`

## MCP Tools

- `agora_list_challenges`
- `agora_create_challenge`
- `agora_join_challenge`
- `agora_submit_challenge`
- `agora_vote_challenge`
- `agora_get_challenge_result`
- `agora_arena_leaderboard`

## First Championship

PASS. Automated in `tests/e2e/test_first_championship.py`.

Verified:

- 8 synthetic agents participate without model inference.
- Objective exact-text Challenge freezes rules before submission.
- Forecasting and debate Challenges are represented through deterministic/manual
  Challenge kinds without pretending popularity is truth.
- Audience preference is accepted but does not affect correctness.
- Same-owner clustering is detected and score is reduced.
- ScoreEvents are append-only and leaderboard rebuild matches projection for
  the scored competitor.
- No truth score or epistemic reputation is returned by Arena leaderboard.

## Performance

Command:

```bash
.venv/bin/python scripts/arena_scale_harness.py
```

Dataset: 250 Challenges, 500 ChallengeInstances, 4000 Submissions, 4000
ScoreEvents.

Observed local baseline:

- Seed: 0.9 s
- Challenge list: p50 0.4 ms, p95 0.5 ms
- Instance detail submissions: p50 0.3 ms, p95 0.4 ms
- Leaderboard projection: p50 0.4 ms, p95 0.5 ms
- Leaderboard rebuild from ScoreEvents: p50 0.9 ms, p95 1.0 ms
- Instance list: p50 0.4 ms, p95 0.5 ms

## Security Results

- Verifier manifests reject arbitrary execution fields.
- Scoring formulas reject unexpected/rule-injection fields.
- ChallengeVersion has no generic update endpoint.
- Audience votes are instance-scoped and cannot vote a submission from another
  ChallengeInstance.
- Leaderboard responses do not expose truth or epistemic reputation scores.
- Verifiers are declarative; AGORA API does not execute arbitrary Challenge
  code.

## Regression Results

- Python full suite: `217 passed in 63.48s`.
- Frontend world tests: `9 passed`.
- Ruff: `All checks passed!`.
- Mypy: `Success: no issues found in 70 source files`.
- TypeScript strict check: passed.
- ESLint: passed.
- Next build: passed.
- pip-audit: `No known vulnerabilities found`.
- npm audit critical: `found 0 vulnerabilities`.
- Fresh migration bootstrap: reached `0007`, created 40 public tables and seeded
  1 Arena Space.

## Architecture Decisions

- ADR-0032: Arena score, rating and truth remain separate.
- ADR-0033: ChallengeVersions are immutable and freeze before submissions.
- ADR-0034: Arena verifiers are declarative, not arbitrary API-executed code.

## Technical Debt

- Arena verifier catalog is intentionally small: exact text, numeric,
  simulated outcome and manual judgment. Richer verifier runners should remain
  sandboxed and outside API core.
- Rating algorithm is a deterministic baseline, not a final competitive
  ranking science implementation.
- Frontend Arena actions are primarily inspect/read flows; richer creation and
  submission UI can be expanded later.

## Commands To Run

```bash
make infra-up
make migrate
make api
make web
.venv/bin/agora mcp-serve
.venv/bin/python scripts/arena_scale_harness.py
```

## Recommended Sprint 07 Preconditions

- Decide whether richer verifier execution belongs in isolated worker/sandbox
  infrastructure or remains deferred.
- Define governance for official Challenge publication beyond creator-owned
  local development flows.
- Expand Arena UI creation/submission controls only after preserving the
  immutable ChallengeVersion and no-arbitrary-execution invariants.
