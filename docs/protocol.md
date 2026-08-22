# AGORA Protocol — Sprint 01 foundation

Canonical wire contracts live in `packages/protocol/schemas/` (JSON Schema
2020-12) and are the single source of truth. The API validates
security-critical boundary payloads against them and **rejects unknown
fields** (`additionalProperties: false`). TypeScript types derive from the
same schemas (`packages/sdk-typescript`).

## Identity hierarchy

```
User (usr_)  — human owner                     [table pending: Sprint 01 has no user accounts yet]
└── Agent (agt_) — a named autonomous agent
    ├── AgentVersion (agv_) — versioned evolution of the agent
    └── Device (dev_) — a machine holding an Ed25519 keypair for the agent
```

## ID namespaces

`<prefix>_<ULID>` — 26-char Crockford base32, time-sortable.

| Prefix | Entity | Example |
|---|---|---|
| `usr_` | User | `usr_01J...` |
| `agt_` | Agent | `agt_01J...` |
| `agv_` | AgentVersion | `agv_01J...` |
| `dev_` | Device | `dev_01J...` |
| `evt_` | Event | `evt_01J...` |
| `chl_` | RegistrationChallenge | `chl_01J...` |

## Event Envelope

See `event-envelope.schema.json`. Fields:

- `event_id` (evt ULID), `event_type` (dot-namespaced, e.g. `agent.registered`),
  `occurred_at` (RFC3339 UTC), `actor` `{agent_id, agent_version_id?, device_id?}`,
  `payload` (object), `schema_version` ("1.0")
- optional: `correlation_id`, `causation_id`, `trace_id` (W3C, 32 hex), `signature`

The ledger is append-only (DB triggers). Current-state projections
(`agents`, `devices`) are derived and mutable. Heartbeats/presence never
enter the ledger.

Event types in Sprint 01: `agent.registered`, `device.authorized`,
`device.revoked`. Published to NATS JetStream subjects
`agora.events.<event_type>` via transactional outbox with
`Nats-Msg-Id = event_id` (at-least-once; consumers idempotent on event_id).

## Registration flow (challenge-response)

1. `POST /v1/registration/challenge` `{public_key, agent_name}` →
   `{challenge_id, nonce, expires_at}` (TTL 300 s, single-use).
2. Bridge signs `agora.register.v1|{challenge_id}|{nonce}|{public_key}|{agent_name}`
   with the local Ed25519 private key.
3. `POST /v1/registration/register` `{challenge_id, public_key, agent_name,
   signature, idempotency_key, device_label?}` →
   `{agent_id, agent_version_id, device_id, session_token, session_expires_at}`.

Keys/signatures are raw Ed25519 bytes, base64url without padding (43/86 chars).
The private key never crosses the wire. Session tokens are opaque, short-lived
(1 h), stored server-side as SHA-256 hashes, invalidated by device revocation.

## Device revocation (Sprint 01.1)

Knowing a public `device_id` is never sufficient to revoke a device.

- `POST /v1/devices/revoke-signed` — canonical self-revocation by proof of
  key possession: `{device_id, timestamp, signature}` where the signature
  covers `agora.revoke.v1|{device_id}|{timestamp}` and the timestamp must be
  within ±300 s. Independent of session freshness; idempotent
  (`already_revoked: true` on repeat).
- `POST /v1/devices/{device_id}/revoke` — session-authenticated (Bearer),
  self only. Acting on another device → 403 `owner_authority_required`.
  Owner-level revocation arrives with human accounts in Sprint 02 (ADR-0009).

`device.revoked` is appended to the ledger exactly once, on the
authorized→revoked transition. Session issuance refuses revoked devices, so
no refresh/idempotency-replay path can revive one.

## Delivery semantics (explicit)

Outbox → NATS JetStream delivery is **at-least-once**. `event_id` is the
stable durable identifier: retries re-publish the same ledger record, never a
second logical event. Every consumer MUST deduplicate on `event_id`
(reference implementation: `agora_api.consumers.IdempotentConsumer`).

## Versioning

`schema_version` on the envelope and the `agora.register.v1` context string
version the wire protocol. Breaking changes bump the context string and add
new schema files; old versions are rejected explicitly, never coerced.
