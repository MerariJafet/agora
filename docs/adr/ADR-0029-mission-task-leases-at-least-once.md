# ADR-0029: MissionTask Leases and At-Least-Once Execution

Status: Accepted · Date: 2026-08-23

## Decision
A MissionTask claim (self-service `claim_mission_task` or coordinator-driven
`assign_task` behind A2A delegation, ADR-0026/ADR-0027 companions) is a
time-boxed lease: `lease_expires_at` plus a monotonically increasing
`attempt` counter, taken under `SELECT ... FOR UPDATE` on the task row.
There is no separate scheduler process, no job queue, and no distributed
consensus — recovery is a plain query
(`missions_service.expire_stale_leases`) that returns any task whose lease
expired while still `assigned`/`running` back to `ready`, clearing
`assigned_agent_id`, without marking it failed.

Submission is attempt-tagged: `submit_mission_task` accepts an optional
`attempt` number and rejects (`409 stale_attempt`) a submission whose
attempt doesn't match the task's *current* attempt. This closes a real gap
found while building the A2A adapter (S5.1-T05): without it, a very late
result from a superseded attempt — the same agent re-claiming after its own
lease expired, with the old execution's result arriving after the new one
started — could silently overwrite a newer attempt's outcome. Resubmission
of the *current* attempt remains idempotent (a no-op if already
`submitted`).

## Rationale
Explicit constraints: "Do not create a Kubernetes-style distributed
scheduler unnecessarily" and "Do not pursue distributed exactly-once
execution." At-least-once with an idempotent submit step and an attempt
guard gives the practical guarantee Missions need — a task is never lost to
a crashed worker, and a stale result is never mistaken for the current
one — without a second infrastructure component.

## Consequences
- Duplicate delivery of the same attempt's result (e.g. an A2A redelivery)
  is a safe no-op; a result from a stale attempt is a clean rejection, never
  silent data loss in either direction.
- If a future sprint needs true fencing across independent AGORA
  deployments (not just independent Bridges against one AGORA instance),
  that is the trigger to revisit the single-Postgres lease approach.
