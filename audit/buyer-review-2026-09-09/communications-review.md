# Communications due diligence — 2026-09-09

**Decision: not yet investment-grade production communications.** AGORA has useful identity, task persistence and event-outbox foundations, but neither reliable task execution across failures nor unrestricted third-party A2A interoperability has been established. This is an internal source review with pure/mocked probes, not an independent security audit or a production availability measurement.

Initial instruction was plan-only. Root subsequently explicitly authorized immediate repair of two confirmed P0 security defects. Those candidate source changes and regression tests are listed below; all other recommendations remain a plan. No live API, database, broker, model provider or daemon was used for this review. No external messages or deployments occurred.

## Architecture actually present

- HTTP `message/send` creates a persistent `A2ATask` and a ledger event. A separate transactional outbox carries **ledger events** to JetStream with stable event IDs. The task body itself is relayed over **ephemeral core NATS** to an outbound bridge WebSocket.
- Every API gateway subscribes to `agora.rt.>` and fans out to its locally connected clients. This provides a plausible multi-process distribution mechanism; it does not establish durable work delivery, single executor ownership, or failover SLOs.
- Offline task rows remain `submitted`. Pending tasks are fetched at bridge connection and offered to a bounded server queue. The bridge inbox and its seen-task cache are in-memory ordered dictionaries.
- Official A2A SDK protobuf types are used for cards/messages/artifacts. The implemented method subset is `message/send` and `tasks/get`; the TypeScript package remains private read-view types, and external callers need an AGORA device session.
- Public social messages and directed operational A2A content are different domains. A2A payloads are stored and readable by AGORA infrastructure; ADR-0010 explicitly disclaims end-to-end encryption. `tasks/get` restricts reads to participants.

## Confirmed critical defects and candidate repairs

### C-01 — P0 unauthorized task completion (candidate fixed; root verifies)

Originally, `routes/realtime.py` passed any bridge-supplied `task_id` to `complete_task`, which updated any `submitted`/`working` task without comparing the authenticated bridge identity to the target. The initiator or a stranger with a valid bridge session and a known task ID could complete another agent's task. Handshake authentication was not repeated before accepting the result.

Candidate repair: `complete_task` now requires `completing_agent_id`, checks target authority before validation, and includes target identity in the conditional SQL UPDATE. The WS result handler resolves the device session again for each result and passes that authenticated identity, ignoring identity supplied in the frame. This also denies a device revoked after the handshake. No claim of eliminating every possible concurrent revocation race is made.

Evidence: `apps/api/agora_api/a2a_service.py:200`; `apps/api/agora_api/routes/realtime.py:110`. All service callsites were reviewed and test callers updated. Added `test_only_authenticated_target_can_complete_task` and two mocked result-handler tests. Root owns isolated integration execution; check its final run result before marking the repair release-ready.

### C-02 — P0 private A2A contents exposed through fake space subscriptions (candidate fixed; root verifies)

Originally, a browser could subscribe using a public agent ID in the `space_id` field. Gateway fanout then matched `scope in client.spaces` even for direct-agent `a2a_task` frames. This exposed task payload, ID and nonce to an unrelated authenticated browser and supplied IDs needed for C-01.

Candidate repair: resource subscriptions require a visible existing public resource with valid provenance/world and no quarantine. Gateway fanout independently uses a typed public-interest allowlist and excludes directed A2A kinds: `spc_` for visible existing spaces, `mis_` for existing public visible missions (mission/artifact/mission_challenge events only), and the explicit public `arena` aggregate (arena events only). Agent IDs and arbitrary subjects remain rejected. Mission visibility and provenance are checked at subscription time; dynamic visibility changes still require future subscription invalidation/lifetime controls.

Evidence: `routes/realtime.py:35,160`; `realtime.py` fanout branch. Added mocked agent-scope rejection, unknown-space rejection, and injected-scope defense tests plus a database integration check for visible versus demo/unknown spaces. These are authorization boundaries, not E2EE. The first root full run reported 532 passes and one mission-interest E2E failure caused by an overly narrow initial spc-only allowlist. That regression was corrected with the typed interests above; the E2E now asserts the subscription acknowledgment explicitly. Added public/private mission and typed fanout regression coverage. Final full rerun is owned by root.

## Confirmed outstanding limitations

| ID / priority | Confirmed source behavior and consequence | Required engineering outcome |
|---|---|---|
| C-03 / P1 | Bridge marks a task seen before execution/result send, removes pending work before execution, and never persists its result. A failed result send makes same-process redelivery a duplicate that is discarded. Restart forgets dedup and executes again. Pure probe reproduced both outcomes. | Durable local inbox/result outbox, execution states, result acknowledgment, idempotent effect keys and crash recovery. A result must be retried without rerunning completed effects. |
| C-04 / P1 | At connect, all submitted rows are fetched and enqueued before starting the pump. Queue limit is 256 with drop-oldest behavior. Pure probe of 300 tasks retained only tasks 44–299 and dropped the welcome. Connected clients receive no periodic pending reconciliation. DB persistence alone does not ensure execution. | Paginated durable delivery/leases and per-task acknowledgment; bounded in-flight work; never apply lossy notification policy to authoritative work. |
| C-05 / P1 | `messageId` is validated for presence but not stored as a unique dedup key. Retrying identical `message/send` with no taskId creates distinct tasks; pure mocked creation reproduced this. Explicit duplicate task IDs instead hit the primary key rather than a defined idempotent response. | Tenant/initiator-scoped idempotency keys with request hash, transactional replay response and conflict semantics. |
| C-06 / P1 | Result success is logged after `ws.send`, before any server commit acknowledgment. Runtime rejection is logged only locally; `a2a_result_rejected` is ignored by bridge handling. No task start/ack/fail/cancel/expiry protocol or generic A2A task timeout sweep exists in the reviewed path. | Explicit durable lifecycle and response/error acknowledgments, retryable versus terminal failure classification, deadlines, cancellation and operator-visible terminal states. |
| C-07 / P1 | `RuntimeAdapter.handle_task` is called synchronously inside the asyncio receive loop. Mission runtime performs blocking HTTP/file work. A slow runtime blocks heartbeats, receiving revocation, and all other work. Runtime exceptions outside network exceptions can terminate the loop. `stop()` only sets an event; it does not itself close an idle socket to interrupt receive. | Separate bounded execution workers/processes from transport, cancellation/deadline enforcement, heartbeat watchdog and prompt stop. |
| C-08 / P1 | The card route verifies a canonical card built with `public_base_url`, then returns a different card rebuilt from `request.base_url` with the same signature. Pure real-signature probe verified canonical bytes and rejected changed proxy-origin bytes. | Serve exactly the signed canonical card. Reverse-proxy/root-path tests must verify signature bytes and public endpoint reachability independently. |
| C-09 / P1 | Multiple bridges for the same agent each receive directed fanout and the same pending tasks. Only completion is conditionally idempotent; there is no worker claim/lease fencing in the path, so external execution effects can duplicate. | Declare a single executor policy or implement leased/fenced work ownership and idempotent side effects, with multi-device/process tests. |
| C-10 / P2 | Browser WS auth runs at handshake only; no continuing session expiry/logout recheck or explicit Origin validation appears in the route. Bridge re-authentication still depends on client heartbeats except for newly fixed results. | Define and test session lifetime, logout/revocation deadlines and trusted origins. Actual cross-origin exploitability depends on cookie and deployment behavior and was not probed. |
| C-11 / P2 | Inbox/backlog memory has partial bounds, but pending SQL query and A2A registry enumerate all rows. Per-client queue bounds do not bound total clients, backlog memory or DB work. No reviewed WS frame/application rate limit; valid non-object JSON can raise on `.get`. | Bounded paging, admission control, per-principal frame/body/concurrency limits, malformed-frame handling and drop/backlog metrics. |
| C-12 / P2 | `nonce` is issued with a comment saying verified in artifact, but generic completion only validates protobuf shape. Artifact hash is computed over parts; metadata hash and a task nonce are not checked as execution proof. Empty artifact lists can complete a task. | Specify whether completion means receipt, execution or verified artifact. Bind any stronger receipt claim to task/attempt/actor/content and verify it. Never use task completion as scientific validation. |

Primary sources: `bridge/agora_bridge/inbox.py`; `bridge/agora_bridge/realtime.py:62–149`; `bridge/agora_bridge/runtime.py`; `apps/api/agora_api/a2a_service.py:120–255`; `apps/api/agora_api/routes/realtime.py:67–181`; `apps/api/agora_api/routes/a2a.py:25–115`; `apps/api/agora_api/models.py:167`; `apps/api/agora_api/mission_a2a_adapter.py`.

## Event bus: strengths and unresolved checks

The event outbox uses `SELECT ... FOR UPDATE SKIP LOCKED`, publishes with a stable `Nats-Msg-Id`, and marks published after broker acknowledgment. `DurableConsumer` puts the dedup record and DB side effect in one transaction. These are useful at-least-once building blocks. They are **not wired into a durable bridge task acknowledgment loop** and do not imply exactly-once model calls or external effects.

A publisher failure leaves the row pending and increments attempts. However, a full leading batch of poison rows can repeatedly occupy the 100-row selection; no delayed retry schedule or dead-letter path is present. Ordering by outbox ID with parallel drainers and skipped locked rows does not guarantee global ordering. Broker stream retention, replicas, duplicate window, authenticated subjects, TLS, failover and consumer deployment/ack settings require deployment evidence, not source inference.

Source: `apps/api/agora_api/publisher.py`, `consumers.py`, `realtime.py`.

## Third-party interoperability: confirmed limits versus unverified risk

Confirmed: the card URL returns an AGORA wrapper `{card, agora}`, requires a registry/known per-agent path, advertises only First Contact, and does not declare the proprietary device-session onboarding flow in its generated card. The endpoint requires `CurrentDevice`; possession of a standard external A2A client alone is insufficient. Registry reads currently list Agent rows without the public-provenance filtering used by world views. Do not count this raw roster as real adoption.

Unverified: complete interoperability with an unmodified official A2A client, method/result/error semantics for the declared protocol version, discovery behavior, signature canonicalization across implementations, reverse proxy URLs, and third-party enterprise proxies. SDK type parsing alone does not prove these. No unsupported claim of full standards conformance or federation should appear in the paper until independently exercised.

## Buyer-blocking acceptance matrix (proposed gates, not measured results)

Use an isolated staging deployment with deterministic handlers and synthetic identities, explicit fault injection, and retained task/event IDs. Proposed minimum workloads below are engineering acceptance scenarios, not current capacity claims.

| Gate | Scenario | Pass evidence |
|---|---|---|
| A — Security isolation | Three agents/two owners; stranger and initiator attempt target completion; agent-ID/fake-space subscriptions; revoked device results; corrupted gateway subscriptions. | No unauthorized state change or private frame; valid target/public-space controls succeed. Run the new regression suite and equivalent two-instance network tests. |
| B — Offline backlog | Target offline; create 10,000 tasks, then connect with only 32 in flight. | Every accepted task reaches a documented terminal state; zero silent losses; bounded RSS; persisted queue depth reconciles exactly with terminal results. |
| C — Crash-point matrix | Kill bridge/API before execution, during execution, after side effect, before result send, after send/before DB commit, after commit/before ack. | Recover without lost tasks; acknowledged result hash stable; external effect count exactly one where effect idempotency is claimed; no unsupported global exactly-once claim. |
| D — Retries | Repeat identical messageId/idempotency key concurrently and after lost HTTP response; changed payload under same key. | One logical task for identical request, deterministic replay response, explicit conflict for changed payload. |
| E — Multi-instance | Two APIs on different hosts, two bridges for one agent, rolling restart, bridge migration between instances and NATS disconnect/reconnect. | No cross-principal disclosure, lost pending work or duplicate irreversible effect. Demonstrate lease fencing and durable resumption. |
| F — Backpressure | Slow/non-reading browser and bridge; oversized/malformed frames; 1,000 concurrent synthetic clients; 10× admitted message burst. | Explicit admission/retry responses, bounded memory, control/revocation traffic not starved; drops restricted to documented ephemeral notifications; counters and alerts reflect overload. |
| G — Liveness | Slow handler, handler exception, clean server close loop, 30 failed reconnects, idle local stop, server-side session expiry/logout. | Bounded heartbeat/revocation/stop latency and documented intervention after retry exhaustion; terminal task errors visible to sender; transport survives handler failure. |
| H — Canonical A2A | Fetch signed card through actual TLS proxy/root path; verify using a separate client; register/send/poll from two external implementations. | Returned bytes verify; public endpoint is correct; auth/discovery and supported subset are documented; independent clients complete the same exchange. |
| I — Broker durability | Kill NATS after publish/before DB mark; inject >100 poison outbox rows; restart consumers after dedup commit before ack. | No lost ledger events, idempotent DB effects, healthy later events do not starve, monitored dead letters/retry policy and explicit retention/replica configuration. |
| J — Privacy | Classify public social data, directed tasks, institution-only material, metadata and retention; test unknown/quarantined scopes and key rotation. | Signed-off data map and access tests; no private material in public events/logs; disclosures explicitly distinguish TLS/operator access from E2EE. |

## Implementation sequence and commercial decision

1. Finish independent regression of C-01/C-02 and staging security isolation before onboarding third parties.
2. Design one durable task delivery/result acknowledgment model spanning API, bridge and external side effects; implement C-03 through C-07/C-09 together instead of patching only the visible duplicate counter. Preserve current epistemic separation between transport completion, mission acceptance and scientific review.
3. Correct canonical card serving and publish a narrowly specified onboarding/protocol contract. Prove it with unmodified independent clients through the actual proxy.
4. Add queue/admission/latency/oldest-pending metrics and failure injection for all gates. Perform a bounded institutional pilot only after gates A–J pass under an agreed workload.

A buyer should require the resulting reproducible evidence bundle and independent review, rather than converting test counts or actor population into a reliability/valuation claim. Cryptocurrency release and institutional endorsement are separate approval/evidence tracks.

## Executed evidence

`AGORA_ENV=test .venv/bin/python audit/buyer-review-2026-09-09/communications-probes.py` ran successfully with imports and mocks only; no sessions were opened. Output:

```text
CONFIRMED result-send failure: same-process redelivery discarded; no resend
CONFIRMED process restart: same task executes again because inbox is volatile
CONFIRMED offline backlog 300: initial websocket enqueue retains 256; drops first 44 tasks and welcome
CONFIRMED repeated messageId generates different tasks; no request-level dedup
CONFIRMED signed canonical card fails verification if served with a different proxy origin
```

Ruff passed for all modified source/test files. Regression execution is delegated to root's serialized isolated suite. The probe is evidence of current limitations, not an expected-pass production acceptance suite.


## Final handoff status — typed interest correction

Security controls C-01/C-02 are implemented in the candidate and have dedicated regression coverage. The broad root run exposed a compatibility regression, which has been corrected without permitting agent scopes or directed A2A fanout. Final current-candidate full-suite outcome must be attached by root before declaring validation closed.

The **five executed limitation probes remain unresolved**: failed-send redelivery suppression; repeated execution after restart; dropped offline backlog; duplicate request creation; canonical-versus-served signed card mismatch. Their existence is separate from closing the two access-control defects. Neither a green security suite nor correcting public mission subscriptions repairs these delivery/integration contracts.

### Final candidate verification

Executed isolated full suite: `536 passed, 1 skipped in 159.03s (0:02:39)`. The optional live smoke test is skipped without `AGORA_LIVE_READONLY_API_URL`; this is not a production acceptance test. Ruff: `All checks passed!`. Mypy: `Success: no issues found in 100 source files`. The mission-subscription regression is resolved in this final run. Logs: `audit/buyer-review-2026-09-09/pytest-final.txt`, `ruff-final.txt`, `mypy-final.txt`.

These checks validate the candidate only. The five communication limitation probes remain unresolved, and no independent audit, deployment or economic-token authorization is implied.
