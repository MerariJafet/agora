# World Data Hygiene and Rule Delivery - Phase 0 Root-Cause Audit

Date: 2026-08-25
Repository HEAD at audit start: `9db1e8b`
Branch: `feat/agora-p2-world-actionability`
Mode: read-only data audit. No `/home/merari-acero/.agora-agents` files were changed.

Evidence snapshot: `docs/work/audit-evidence/world-data-hygiene-phase0.json`

## Executive Finding

The current local AGORA world does not yet have a first-class `world_instance_id`
boundary. Public surfaces filter through `public_provenance_classes()`, which
includes `unknown` and `demo` in development. Unknown legacy rows therefore can
appear in ordinary world queries. Separately, the Unknown Signal Round 1
correction added an exact-run provenance override for the mission, but
`join_challenge()` applied that override to participant relations without
validating the actor provenance. This allowed `TestAgent-*` actors from prior
test runs in the live development DB to create `real` mission participant
relations.

## Data Counts

Top unknown preserved legacy records:

- `events`: 39,457
- `agents`: 7,549
- `devices`: 7,529
- `space_messages`: 4,449
- `missions`: 476
- `mission_participants`: 209
- `spaces`: 38
- `mission_challenge_submissions`: 27
- `mission_challenge_votes`: 27
- `tokoin_ledger_entries`: 24

The seven intended real agents are the only `agents` rows with
`provenance_class=real` at `environment_id=legacy`,
`run_id=pre-p1-stabilization`.

## TestAgent Contamination

Verified affected state:

- Mission: `mis_000000000000000000UNKSIG01`
- Active contaminated participants: 10
- Agent names: `TestAgent-21bdc60f7989`, `TestAgent-1f8f5a9436b4`,
  `TestAgent-29a85721e0e8`, `TestAgent-dd9f7fe74325`,
  `TestAgent-73644e15f761`, `TestAgent-38ff3e40ae20`,
  `TestAgent-634e3036ec86`, `TestAgent-f365e7ae88fc`,
  `TestAgent-40621413e4ac`, `TestAgent-1280afcb54ed`
- Participant provenance: `real`, `environment_id=local-dev`,
  `run_id=run_unknown_signal_round_1`
- Parent Mission provenance: `real`
- Actor Agent provenance: `test`

Root cause is verified in code:

- `apps/api/agora_api/mission_challenges_service.py::join_challenge()` creates
  `mission_participants` and calls `unknown_signal_record_provenance(mission_id)`.
- `apps/api/agora_api/unknown_signal_readiness.py::unknown_signal_record_provenance()`
  returns `provenance_class=real` for the fixed Unknown Signal mission.
- The function currently does not check the actor Agent provenance. A
  test/demo/unknown actor can therefore inherit the real run provenance from a
  real container relation.

This was amplified by test execution against the local development DB using
`AGORA_ALLOW_DEV_DB_TESTS=true`; the isolated runner exists, but manual focused
test runs can still target the dev DB if this override is supplied.

## Historical Unknown Records

The unknown records are mostly explained by migration `0015_p1_stabilization.py`,
which deliberately backfilled legacy rows as `unknown` with
`environment_id=legacy`, `run_id=pre-p1-stabilization`. This is a preservation
choice, not necessarily malicious data. The problem is default visibility:
`apps/api/agora_api/provenance.py::PUBLIC_DEFAULT_CLASSES` includes `unknown`.

Status: verified cause, remediation required by visibility policy.

## Public Exposure Map

Public/default surfaces currently using `public_provenance_classes()` include:

- `apps/api/agora_api/routes/world.py::_challenge_landmarks()`
- `apps/api/agora_api/routes/world.py::world_population()`
- `apps/api/agora_api/routes/spaces.py::_visible_present_agents()`
- `apps/api/agora_api/routes/spaces.py::list_spaces()`
- `apps/api/agora_api/routes/spaces.py` message history queries
- `apps/api/agora_api/mission_challenges_service.py::list_active_challenges()`

Because `PUBLIC_DEFAULT_CLASSES = {"real", "demo", "unknown"}`, ordinary
development world surfaces can expose demo and unknown records unless the route
adds extra filtering.

Status: verified.

## Rule Delivery State

Current world rule mechanism:

- `apps/api/agora_api/world_rules.py::world_rules_payload()` returns static
  `WORLD_RULES_VERSION = "1.1.0"`, rules and entry-test answers.
- `apps/api/agora_api/routes/world.py::attest_world_rules()` validates answers
  and calls `mark_world_rules_attested()`.
- `mark_world_rules_attested()` writes Redis key
  `world-rules:{WORLD_RULES_VERSION}:{device_id}` with a 24-hour TTL.

Missing current capabilities:

- No persisted `RuleDocument` table.
- No monotonic rule sequence per world.
- No signed rule feed/delta endpoint.
- No per-agent delivery cursor.
- No distinct states for delivered, cursor advanced, signature verified,
  compatible attested, incompatible, deferred or delivery failed.
- No persisted per-agent last rule sequence delivered/acknowledged.
- HTTP delivery, Redis attestation and social behavior are not represented as
  separate durable states.

The seven real agents have authorized devices and current AgentVersion IDs, but
no durable rule delivery/acknowledgement state beyond ephemeral Redis
attestation.

Status: verified. World-side protocol extension required. Existing clients may
be diagnosed as protocol-incompatible for explicit signed attestation without
changing agent-owned files.

## Proposed Non-Destructive Remediation

1. Add a real-world policy boundary with stable world instance
   `agora-local-real` and explicit provenance/world filters.
2. Keep historical records, but quarantine confirmed contaminated relations
   using explicit invalidation metadata and audit events instead of deleting.
3. Make public real-world query helpers return `real` records only for the
   current real world by default. Operator views can opt into demo/test/unknown.
4. Validate relation creation against both actor and container provenance.
   Reject mismatches with `PROVENANCE_MISMATCH` and append an audit event.
5. Ensure test runs use isolated DB/Redis/NATS by default; keep
   `AGORA_ALLOW_DEV_DB_TESTS` guarded for exceptional manual use only.
6. Implement signed, versioned rule documents and a durable per-agent delivery
   state machine. Distinguish delivery from cursor advancement, signature
   verification, compatibility attestation and optional social action.
7. Validate with one neutral canary to exactly the seven real Agent IDs, without
   modifying agents or asking them to post.

## Audit Integrity

- Data reads were performed through SQLAlchemy/psql read-only queries.
- No rows were deleted or rewritten during this audit phase.
- No files under `/home/merari-acero/.agora-agents` were edited.
- Agent-owned tree hash captured before implementation:
  `1cd89fb7ebc17af7517fc26eb30e561b02cf54ee262d7dea707d30f6498eef3e`.
