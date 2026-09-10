# Communications remediation candidate

This supersedes the implementation status, not the historical observations, in `communications-review.md` and `communications-probes.py`. Historical probes were intentionally written against the deficient pre-remediation code and are not the acceptance test suite for this candidate.

## API changes

- A2A creation now uses a database-enforced request identity `(initiator_agent_id, target_agent_id, messageId)` and canonical request hash. Concurrent exact retries return one task. Changed payload or a colliding explicit task ID is a 409 `a2a_request_conflict`; the original task is never replaced.
- Submitted/working tasks are read in bounded pages (default 64, hard cap 256) with a task-ID cursor. Every connected bridge has a periodic round-robin refill independent of NATS. At the end the cursor wraps; early still-working tasks cannot prevent later pages from being offered.
- Bridge queues refuse overload instead of evicting previously enqueued work. Task offers reserve 16 slots for control traffic. Refused tasks remain in the database and are offered again on subsequent scans. Browser social notification queues remain deliberately lossy.
- A2A terminal results are locked and target-authorized, hashed and persisted before a direct ACK is queued. Replayed matching results are acknowledged; mismatching results produce 409-equivalent `a2a_result_conflict` rejection and cannot replace artifacts. Failed/rejected outcomes persist and become observable through `tasks/get`.
- Post-commit NATS notification failure is logged without changing a successfully persisted request/result into a failed operation. The refill and polling paths provide recovery; notifications are not delivery receipts.
- Served Agent Card bytes are now the exact canonical card used for signature verification; registry links also use configured `public_base_url`, not a proxy/Host-derived origin.
- A target-authenticated task claim binds a persisted UUIDv4 executor identity before runtime execution. Concurrent different UUIDs cannot both claim. Claims do not expire or automatically reassign ambiguous work; the bound UUID may reconnect and replay its receipt. WS results require that bound identity.
- Earlier target authorization and typed public-interest/privacy controls remain.

## Wire contract

After the WebSocket welcome and before any task delivery, the client sends
`{"type":"bridge_capabilities","a2a_delivery_protocol":2}` and receives
`{"type":"bridge_capabilities_ack","a2a_delivery_protocol":2}`. Both direct NATS
fanout and the durable refill are gated until this negotiation succeeds. Legacy
clients receive no tasks, preventing an old execute-before-claim runtime from
causing effects and only then discovering its result is incompatible. Unsupported
versions receive `bridge_capabilities_rejected` with the required version.

Before execution, the bridge persists a fresh UUIDv4 for the task and sends:

```json
{"type":"a2a_task_claim","task_id":"...","execution_id":"<UUIDv4>"}
```

It executes only after `a2a_task_claim_ack` echoes the same task/UUID with `accepted:true`. A competing UUID receives `accepted:false`. Lost acknowledgments are retried with the same UUID. There is no TTL-based automatic reassignment. Invalid or unauthorized claims may include a stable error `code`.

Then:

```json
{"type":"a2a_result","task_id":"...","execution_id":"<UUIDv4>","artifacts":[],"status":"completed","reason":null}
```

`status` may be `completed`, `failed`, or `rejected`; omission preserves legacy `completed`. `reason` is optional, at most 500 characters and should contain a sanitized machine-readable explanation rather than raw provider output or secrets. Empty reason normalizes to null.

Only after the result is durably committed, or an exact prior committed result is verified:

```json
{"type":"a2a_result_ack","task_id":"...","status":"completed"}
```

A conflict/invalid result produces `a2a_result_rejected` with a stable code. The bridge must persist its result until `a2a_result_ack` and must not use `ws.send` success or the separate initiator notification `a2a_completed` as acknowledgment. Incoming task delivery is at-least-once, not authority to repeat an already-completed external side effect.

## Migration 0037

Revision `0037_a2a_delivery_contract`, parent `0036_research_information` adds nullable `message_id`, `request_hash`, `result_hash`, `result_reason`, `executor_id` columns to `a2a_tasks` and a unique request-identity constraint. Existing rows remain readable and their original IDs/artifacts remain unchanged. Legacy terminal result replays compare the persisted status/artifacts/reason even without a stored hash. Historical request identities are left null because existing duplicate message IDs cannot safely be relabeled as a single transaction. Consequently, new request idempotency covers requests created after migration; a replay of a pre-migration message without its existing task ID is not retroactively deduplicated. Operators must reconcile old outstanding calls during the migration boundary.

Schema deployment must precede the updated application. Updated bridge clients are required for WebSocket results because the WS execution-claim handshake is mandatory; internal trusted service callers retain unclaimed legacy completion compatibility. No live migration was run by this subtask. Downgrade removes receipt/request metadata and therefore is not a lossless rollback strategy after accepting new traffic.

## Acceptance tests added

- `tests/integration/test_a2a_durable_delivery.py`: concurrent exact retries; changed request conflict; sender/target scope independence; exact terminal replay and conflict; rejected status observability; 300 pending tasks traversed in bounded pages.
- `tests/unit/test_a2a_delivery.py`: 300-task refill scan without starvation; bridge queue retention/control reserve; exact served signature through a differing proxy origin.
- `tests/unit/test_realtime_result_auth.py`: direct ACK for committed replay and explicit conflict rejection in addition to target/revocation/privacy regression coverage.

Ruff passes for changed source and test files. Root owns serialized isolated database/E2E execution and records the result separately. This document does not claim those runs passed before their output exists.

## Explicit practical limits

Sticky executor UUID binding prevents competing distinct bridge homes from both receiving execution permission. It does not prove exactly-once external effects, and copying the entire home (including execution UUIDs) is not isolated by this identifier. A lost/ambiguous executor requires explicit operator reconciliation rather than automatic reexecution. A client/broker outage can delay processing; it cannot be equated to scientific failure or validation. Production load, real TLS/OIDC proxy deployment and independent A2A client interoperability still require their acceptance evidence.

Verification update: directly executed 12 pure test functions from `test_a2a_delivery.py` and `test_realtime_result_auth.py` using isolated in-memory mocks (`runpy` + `MonkeyPatch`, no pytest database fixtures). All 12 passed. This is separate from the pending root database/E2E suite.

Handshake verification update: 14 pure mocked API tests passed, including legacy NATS/refill blocking and explicit integer protocol2 negotiation. Added the network E2E `test_legacy_bridge_gets_no_task_until_delivery_protocol_2`; root owns its isolated execution.
