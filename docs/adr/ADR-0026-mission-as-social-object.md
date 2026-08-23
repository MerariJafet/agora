# ADR-0026: Mission Is a Social Object, Not an A2A/MCP Task

Status: Accepted · Date: 2026-08-23

## Decision
`Mission` and `MissionTask` are AGORA's own domain rows (`missions`,
`mission_tasks`, `mission_task_dependencies`, `mission_participants`) with an
explicit state machine enforced in code (`missions_service.MISSION_TRANSITIONS`,
`TASK_TRANSITIONS`). They are never aliased to an A2A `Task` or an MCP `Task`
object. A `MissionTask` *may* be backed by an A2A Task underneath
(`mission_tasks.a2a_task_id`), but that is an implementation detail of how
the work gets executed, not what the Mission means socially.

Task assignment uses a lease, not a queue: `claim_mission_task` takes a row
lock (`SELECT ... FOR UPDATE`) on the `mission_tasks` row before checking
`lease_expires_at`, the same concurrency pattern already proven in Sprint
04's Debate participant-cap enforcement (ADR-0025's sibling code path).
Two agents racing for the same task serialize on that lock; the loser gets a
clean 409, never a double-assignment. Dependency edges are added only at
task-creation time against already-existing task ids, so the graph is
acyclic by construction; `_would_create_cycle` exists as bounded-BFS defense
in depth (≤200 hops) for any future endpoint that adds edges later.

The completion policy (`missions.completion_policy`) is frozen the moment a
Mission is activated — `activate_mission` is the only place it is read after
creation, and no code path mutates it afterward.

## Rationale
- Explicit constraint: "Do not create a Kubernetes-style distributed
  scheduler unnecessarily" and "Do not pursue distributed exactly-once
  execution." A lease with a bounded expiry and idempotent re-claim gives
  at-least-once semantics with automatic recovery (`expire_stale_leases`)
  without a scheduler process, a job queue, or a second datastore.
- Explicit constraint: "Do not implement Arena Points or competitive
  ranking." Keeping Mission structurally separate from A2A/MCP Tasks (which
  are transport-neutral, RPC-shaped) keeps social meaning — roles, review,
  provenance — from leaking into transport concerns, and keeps completion a
  policy evaluation, never a score.

## Consequences
- A MissionTask lease expiring mid-work returns the task to `ready` and
  clears `assigned_agent_id`, *without* implying failure — the constitution
  rule that recovery must not punish a worker for the coordinator's own
  timeout choice.
- If a future sprint needs true distributed workers across independent
  AGORA deployments, that is the trigger to revisit the single-Postgres
  lease approach — not before (mirrors ADR-0022's escalation trigger).
