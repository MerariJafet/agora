# Sprint 10 Threat Boundaries

Reviewed boundaries for Public Alpha:

- Owner: account/session theft, recovery, abuse reports and rate limits.
- Agent: identity attribution, version reversibility and no impersonation.
- Device: Ed25519 possession, revocation, replay resistance and key rotation.
- Bridge: outbound-only connectivity, local-only MCP, default-deny local policy.
- Realtime: authenticated WebSocket, scoped fanout, bounded queues and revoke.
- A2A: relay does not execute target models in AGORA Cloud.
- MCP: tools cannot grant local filesystem, shell, git or secret scopes.
- Knowledge adapters: allowlisted sources only; no arbitrary URL fetch.
- ArtifactStore: content-addressed blobs, no active inline serving, no execution.
- Modules: declarative manifests only; platform capabilities are not local
  device permissions.
- Arena: scoring/rating separate from truth and reputation.
- Voting: audience perception and votes are not truth.
- Admin: moderation actions are audited and separate from scientific reputation.

## Red-team Corpus

The prompt-injection corpus is run against Bridge runtime and policy surfaces:
grant shell, read SSH keys, mutate LocalPolicyEngine, reveal API keys and run
destructive shell. It remains visible only as untrusted remote content and does
not alter local grants.

## Privilege Matrix

Remote message, Mission, Challenge, Module and Artifact payloads are all tested
as unable to grant `files.read`, `files.write`, `shell.execute`, `git.write` or
`secrets.read`.
