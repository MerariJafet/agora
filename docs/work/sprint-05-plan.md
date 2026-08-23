# Sprint 05 — Missions & Artifacts: Implementation Plan

Date: 2026-08-23 · Branch: `feat/agora-sprint-05-missions-artifacts`
Baseline: **172 Python + 9 TypeScript, 0 failures**.

## Standards verification
- A2A: continue on `a2a-sdk 1.1.2` (unchanged). MissionTask wraps A2A Task
  correlation as AGORA-side metadata (`a2a_tasks` table already exists from
  Sprint 02) — no canonical A2A payload field is redefined.
- MCP: continue on `mcp 2.0.0`. The official Tasks extension is NOT adopted
  this sprint (feature-detection would add an optional dependency for no
  Sprint 05 requirement — Mission durability lives in Postgres, not MCP).
- ArtifactStore: **local filesystem implementation** is the Sprint 05
  primary (deterministic, zero extra infra, no paid credential). The
  interface is designed so a MinIO/S3 adapter drops in later without
  changing callers — justified simpler implementation per prompt allowance
  ("if practical"); running an extra MinIO container for one sprint's tests
  adds infra surface with no Sprint 05 requirement demanding it.

## Domain additions (migration 0006, additive)
`missions`, `mission_participants`, `mission_participant_roles`,
`mission_tasks`, `mission_task_dependencies`, `artifacts`,
`artifact_versions`, `artifact_reviews`. New ID namespaces: `mis_`, `mpt_`
(participant — reuses agent_id as PK component instead, no separate id
needed), `mtk_` (MissionTask), `art_` (Artifact), `arv_` (ArtifactVersion),
`arw_` (ArtifactReview).

## Key mechanisms
- **Mission state machine**: explicit transition table, each transition
  appends a ledger event in the same transaction as the row change (Sprint
  01.1/04 pattern).
- **Task DAG**: `mission_task_dependencies(task_id, depends_on_task_id)`;
  cycle rejection via a bounded reachability check from the new dependency
  back to the task (graph is small per Mission — no recursive CTE needed at
  this scale, same "Postgres first" posture as ADR-0022).
- **Lease claiming**: `SELECT ... FOR UPDATE` on the mission_task row,
  atomic check-and-set of `assigned_agent_id` + `lease_expires_at` — same
  concurrency pattern as Sprint 04's debate participant-cap lock.
- **ArtifactStore**: streaming upload computes SHA-256 incrementally,
  enforces a byte cap while streaming (never buffers the whole file), writes
  to a quarantine path, and only renames into the content-addressed final
  location after the stream completes and the byte count is verified —
  never before. Content-addressing (`sha256/<hash>`) gives free
  deduplication.
- **Publication boundary**: Bridge-side `agora publish-artifact <path>` /
  MCP `agora_publish_artifact` reads exactly one explicit local path through
  LocalPolicyEngine (`files.read`), refuses directories, refuses symlink
  escape outside the resolved real path, and refuses a small deny-list of
  secret-shaped filenames (`.env*`, `*.pem`, `id_rsa*`, etc.) even if
  `files.read` is granted — this is a hard floor, not a policy the owner can
  accidentally disable by granting `files.read`.
- **Provenance manifest**: canonical JSON (sorted keys) stored in
  `artifact_versions.provenance_manifest` JSONB + its own sha256 recorded
  alongside — changing provenance after the fact is structurally impossible
  because ArtifactVersion rows are never updated.

## Order of work
Schemas → migration 0006 → ArtifactStore + streaming upload/publish →
Mission state machine + task DAG + lease → A2A MissionTask adapter →
provenance/review/revision loop → completion evaluator → MCP tools →
security tests (path traversal, symlink, secrets, tamper, oversized) →
concurrency/failure tests → realtime fanout → frontend Mission Board →
performance harness → ADRs/docs → full regression + First Collaborative
Mission E2E.
