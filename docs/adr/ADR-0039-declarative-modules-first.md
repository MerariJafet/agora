# ADR-0039: Declarative Modules First

## Status

Accepted.

## Context

Sprint 08 lets agents expand AGORA with games, rooms and buildings. Allowing
arbitrary JavaScript/HTML in the privileged application origin would violate
the local-first security model and create immediate XSS/privilege risks.

## Decision

World Builder modules are declarative manifests first. `ModuleManifest`
describes type, capabilities, resources, UI schema, events, inputs/outputs,
knowledge sources, lifecycle and building shape. API core validates and stores
manifests but does not execute submitted code.

## Consequences

- Agents can create new modules without core code changes.
- UI/world renderer can compose buildings locally from safe manifest data.
- More powerful execution, such as WASM, must stay behind an explicit sandbox
  with separate limits and review.
