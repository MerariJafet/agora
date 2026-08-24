# ADR-0040: Module Capabilities Are Not Local Permissions

## Status

Accepted.

## Context

Module authors need to request platform capabilities such as world rendering,
space messaging or Knowledge source references. Those requests must never become
Bridge `LocalPolicyEngine` grants.

## Decision

`CapabilityGrant` records platform/module capabilities only. The allowed
vocabulary excludes `files.read`, `files.write`, `shell.execute`,
`network.external`, `git.write` and `secrets.read`. Static analysis rejects
manifests containing those local permission strings anywhere in the submitted
payload.

## Consequences

- Remote modules cannot grant local machine permissions.
- Module review remains an AGORA-world authorization concept.
- Future sandboxes must keep the same separation from local Bridge policy.
