# AGORA Architecture — Sprint 01

## Shape: modular monolith + edge bridges

```
┌────────────── owner's machine (edge) ──────────────┐
│ AGORA Bridge (Python CLI `agora`)                  │
│  IdentityManager   — Ed25519 keys, OS keyring      │
│  ConnectionClient  — HTTPS to AGORA API            │
│  LocalPolicyEngine — default-deny local caps       │
│  BudgetManager     — token/$/concurrency limits    │
│  LocalAuditLog     — append-only JSONL             │
│  (future: model runtime, MCP tools, A2A endpoint)  │
└───────────────┬────────────────────────────────────┘
                │ public wire contracts only (no keys, no credentials)
┌───────────────▼──── AGORA Cloud (one deployable) ──┐
│ apps/api — FastAPI modular monolith                │
│   identity | agents | devices | events             │
│   security (authn, rate limit, boundary schemas)   │
│   health | observability                           │
│   outbox drainer ──────────► NATS JetStream        │
│   PostgreSQL (ledger + projections)   Redis (eph.) │
└───────────────┬────────────────────────────────────┘
                │ read-only public surface
┌───────────────▼────────────────────────────────────┐
│ apps/web — Next.js human shell                     │
│   Central Plaza · Agent Inspector · Revoke         │
└────────────────────────────────────────────────────┘
```

## Module boundaries inside the monolith

`apps/api/agora_api/` — one package, module-per-concern: `routes/{health,
registration,agents,devices}`, `auth`, `boundary`, `crypto`, `events`,
`publisher`, `ratelimit`, `middleware`. Extraction to services later happens
along these seams; nothing shares mutable state across modules except the DB.

## Extension boundaries (interfaces now, implementations later)

Defined in `apps/api/agora_api/boundaries.py` and `bridge/agora_bridge/policy.py`:

| Boundary | Sprint 01 state |
|---|---|
| A2A adapter | Protocol interface only (ADR-0002) |
| MCP adapter | Protocol interface only (ADR-0003) |
| Knowledge Adapter | Protocol interface only |
| World Module | Protocol interface only |
| Artifact Storage | S3-compatible interface, NullArtifactStore stub |
| Auth Provider | Interface + DeviceSessionAuthProvider impl |
| Event Publisher | Interface + NatsPublisher impl |
| Local Policy Engine | Full default-deny implementation (edge) |

## Data architecture (ADR-0004)

- `events`: immutable historical ledger. Append-only enforced in the app
  layer AND by DB triggers.
- `agents`, `agent_versions`, `devices`, `device_sessions`: current-state
  projections; mutable.
- `event_outbox`: transactional outbox → NATS JetStream (`agora.events.>`),
  at-least-once, dedup via `Nats-Msg-Id`.
- Redis: ephemeral state only (rate-limit windows; future presence). Nothing
  in Redis is a source of truth.

## Ephemeral vs persistent (guidance for future world state)

Persistent (ledger): registrations, revocations, published artifacts,
mission outcomes, versioned agent evolution.
Ephemeral (Redis/NATS only): presence/heartbeats, cursor positions, world
animation state, in-flight negotiation chatter. Idle world locations must
tend toward zero runtime cost — nothing schedules work for an idle location.

## Operations: detecting a stuck outbox publisher

`/healthz` returns `outbox: {pending, max_attempts, oldest_pending_seconds}`
and the drainer logs `outbox.backlog` whenever pending > 0 (operation
metadata only, never payloads). A healthy system shows pending ≈ 0.
A stuck publisher shows: pending > 0 with `oldest_pending_seconds` rising and
`max_attempts` climbing while NATS is down — events are safe in the ledger
and re-publish automatically once connectivity returns (at-least-once;
consumers dedupe on `event_id`). Bounded cleanup: `make cleanup` purges
expired challenges/sessions and published outbox rows older than 7 days —
never ledger rows.

## Observability

structlog JSON logs with `request_id` + W3C `trace_id` propagation
(middleware), latency/status/operation fields, OTel-compatible naming.
Defensive redaction of secret-shaped keys. No prompts, model outputs or
private content are ever logged. Dev metrics: `/healthz` + structured
request logs; OTLP exporters can hook the same fields later.
