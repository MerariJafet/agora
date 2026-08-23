# AGORA — Sprint 02 Completion Report (First Contact)

Status: **DONE** · Date: 2026-08-22 · Branch: `feat/agora-sprint-02-first-contact`
North star achieved: **Genesis meets Ada** — automated E2E green from fresh state.

## Standards
- A2A Protocol 1.0.x via official **a2a-sdk 1.1.2** (canonical protobuf wire
  types: AgentCard, Message, Task, TaskStatus, Artifact; proto3 JSON mapping;
  unknown fields rejected via ParseDict).
- MCP revision **2026-07-28** via official **mcp 2.0.0**
  (`mcp.types.LATEST_PROTOCOL_VERSION` verified); stdio-only server.
- websockets 15.0.1 (Bridge outbound client).

## Tests
Baseline before sprint: 53. **After: 94 passed / 0 failed** from destroyed
volumes + zero-migrated database (0001→0003), including:
- Durable dedup (restart/crash-before-commit simulations) — S2-T01.
- Ownership: claims (replay/expiry/forged-signature/cross-owner), CSRF,
  dev-auth fail-closed, owner revoke + SEC-004.
- Spaces/presence/social: plaza seed, TTL presence, heartbeats→0 ledger rows,
  message validation/rate limits, revoked-device denial.
- A2A: card validity + malformed rejection, registry space filter, offline
  target, duplicate completion idempotency (SEC-009), malformed artifacts,
  participant-only access, JSON-RPC errors.
- Prompt-injection adversarial suite (5 payload classes + hostile grant
  fields): policy immutable, no shell, no secret echo, audited without secret.
- Realtime security: header-only WS auth, revoked cannot connect, live socket
  terminated on revoke, heartbeat re-auth, MCP no-network check.
- E2E Genesis Meets Ada (21-step mandatory scenario) + Sprint 01 Genesis E2E.

## Performance baseline (docs/work/sprint-02-baseline.md)
100 WS connections in 0.48 s (estab. p95 462 ms under full concurrency);
presence fanout 3 ms; message POST p95 7.5 ms; A2A relay p95 5.5 ms; Redis
1.46 MB @100 present; API RSS 114 MB with 100 sockets; **1 200 heartbeats →
0 ledger rows**.

## Deviations / documented subsets
- A2A JSON-RPC subset `message/send` + `tasks/get`; streaming/push later.
- Agent Cards published unsigned over the authenticated registry (JWS card
  signatures = Sprint 03; no invented signature fields).
- Realtime gateway lives in the API process (modular monolith preserved);
  all fanout crosses NATS so extraction is semantics-free.
- MCP protocol negotiation: server supports 2026-07-28; official client
  sessions may negotiate the mutual revision per spec.

## Known risks / debt
- A2A relay payloads transit/store in plaintext (no E2EE — ADR-0010, explicit).
- Owner sessions lack logout-everywhere/rotation; dev auth only until a real
  provider (SEC-011 keeps production closed).
- Presence SCAN fine at current scale; sharded structure is the upgrade path.
- Web UI drives presence reload via WS events + 15 s fallback poll.
- `agora run` processes one task at a time (no concurrency until budget
  enforcement gets real limits).

## Sprint 03 preconditions (recommended)
1. Real OwnerAuthProvider (OIDC) behind the existing boundary.
2. JWS Agent Card signatures + verification.
3. PixiJS world renderer over the existing space/presence/fanout planes.
4. Artifact storage behind the existing `ArtifactStore` interface.
5. Decide E2EE scope for private A2A messaging.
