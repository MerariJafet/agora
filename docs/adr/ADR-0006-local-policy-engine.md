# ADR-0006: Local Policy Engine

Status: Accepted · Date: 2026-08-22

## Decision
Every dangerous local capability on the edge is mediated by
`LocalPolicyEngine` (bridge/agora_bridge/policy.py) with default-deny.
Categories: `files.read`, `files.write`, `shell.execute`,
`network.external`, `git.write`, `secrets.read`. Grants come exclusively
from local owner action (CLI/config file). Pausing the Bridge denies
everything.

## Structural separation of permission universes
Local permissions and AGORA network scopes are different types in different
trust domains. The engine's only input is the local `BridgeConfig`; there is
deliberately no deserialization path from remote payloads into grants, and
`grants_from_remote_payload()` exists solely to make that invariant explicit
and testable (SEC-002).

## Consequences
- A hostile or buggy AGORA Cloud cannot escalate onto owner machines.
- Future mission/tool features must request local permission via owner
  prompts, never via event payloads.
- The audit log records every grant and decision (without secrets).
