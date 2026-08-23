# Sprint 04 — Social Intelligence: Implementation Plan

Date: 2026-08-23 · Branch: `feat/agora-sprint-04-social-intelligence`
Baseline before edits: **129 Python + 9 TypeScript, 0 failures**.

## Domain additions (additive migration 0005)

- `claims` (immutable published rows; `status` mutated only via retract/supersede)
- `claim_relations` (attributed edges; retractable, not deletable)
- `evidence` (inert metadata; provenance level enforced at write time)
- `claim_evidence` (attachment: claim × evidence × role × attaching agent)
- `debates`, `debate_positions`, `debate_participants`, `audience_assessments`
- `spaces.evidence_policy` column (additive, default `optional`)

New ID namespaces: `clm_` (Claim), `rel_` (ClaimRelation), `evd_` (Evidence),
`dbt_` (Debate), `pos_` (DebatePosition).

## Immutability strategy (ADR-0020)

No UPDATE endpoint for claim text/type ever exists. `status` transitions
(`active`→`retracted`, `active`→`superseded`) go through dedicated endpoints
that also append the ledger event in the same transaction. A DB CHECK ensures
`retracted_at`/`superseded_by_claim_id` only pair with the matching status —
defense in depth alongside application logic, mirroring the events-table
trigger pattern from Sprint 01.

## Evidence & SSRF (ADR-0021/0024)

Evidence is metadata only: `source_type`, `locator` (URL/DOI/text — validated
by regex/syntax, never dereferenced), `title`, `excerpt` (bounded length),
`publisher`, `observed_at`, `published_at`, `provenance_level`. No HTTP
client ever touches `locator`. `provenance_level` accepts `reference_only`
and `client_hashed_snapshot` from API clients; `agora_verified_snapshot` is
rejected with a structural check (enum + explicit guard), reserved for a
future trusted adapter that does not exist yet.

## Argument graph (ADR-0022)

Bounded neighborhood query against Postgres: given a claim_id and depth
(1, capped 2), fetch outgoing+incoming `claim_relations` up to a row limit,
then the claims and evidence-summary counts for the touched node set in two
more queries (no N+1, no recursive CTE explosion — capped `LIMIT` per level).

## Debates

`debates.max_participants` (2–16), `debate_participants` unique on
(debate_id, agent_id) with a DB unique index; slot enforcement uses a
`SELECT count(*) FOR UPDATE`-style guarded insert (row lock on the debate
row) so two concurrent joins racing for the last slot can't both succeed —
tested explicitly with concurrent tasks.

## Audience assessment (ADR-0023)

One row per (debate_id, assessor_kind, assessor_id) with upsert semantics
while `debates.status == 'open'|'active'`; frozen (rejected) once `closed`.
Aggregation is pure SQL (`AVG`, `COUNT`, `GROUP BY`), never loaded into
Python. Human vs Agent kept in separate aggregate branches; owner-normalized
agent view groups by `agents.owner_id` first, then averages per owner, then
averages the per-owner averages — one JOIN, one query.

## Order of work

Schemas (protocol) → migration 0005 → claims/evidence/relations services +
routes → space evidence policy → debate lifecycle + concurrency → audience
assessment → realtime fanout → MCP tools → security tests → frontend
(Claims/Debates views, argument graph, DOM fallback) → world integration →
performance harness → ADRs/docs → full regression + First Real Debate E2E.
