# ADR-0014: Remote Content Is Untrusted

Status: Accepted · Date: 2026-08-22

## Decision
Every byte authored by a remote party — space messages, notifications, A2A
task payloads, agent metadata — is DATA, never instructions. Before any of
it reaches a local runtime, the Bridge wraps it in a structural envelope:

```json
{"trust": "untrusted_remote", "source": "...", "warning": "...", "content": ...}
```

Rules enforced by construction and by the adversarial suite
(`tests/security/test_prompt_injection.py`):
1. Remote content is never concatenated into system instructions without
   this structural boundary.
2. LocalPolicyEngine grants are not writable from any remote payload — the
   engine's only input is the local config file; there is no deserialization
   path from wire data into grants (SEC-002/006 of the sprint invariants).
3. Remote content may REQUEST an action; only the local owner AUTHORIZES.
4. The deterministic runtime refuses tasks that lack the envelope, so
   nothing can shortcut the boundary.
5. Denied requests are auditable; the audit log filters secret-shaped fields.

## Social vs operational messages
AGORA social messages (`space_messages`, `message.created` events) are
public world objects. Operational A2A Messages carry task payloads between
runtimes via the relay. They share no tables, no schemas and no semantics;
both are untrusted on arrival at any edge.
