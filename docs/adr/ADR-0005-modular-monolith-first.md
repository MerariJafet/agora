# ADR-0005: Modular monolith first

Status: Accepted · Date: 2026-08-22

## Decision
AGORA Cloud ships as one FastAPI deployable with strict internal module
boundaries (identity, agents, devices, events, security, health) plus
explicit extension interfaces (`boundaries.py`): A2A, MCP, Knowledge,
World Module, Artifact Storage, Auth Provider, Event Publisher.

## Rationale
One team, one deployable, fast iteration; distributed complexity (service
mesh, sagas, per-service datastores) is premature. Boundaries keep future
extraction cheap: modules communicate through interfaces and the database,
never through shared mutable state.

## Consequences
- Docker Compose runs the entire dev stack; no orchestration needed yet.
- Artifact storage remains a stub (`NullArtifactStore`) behind a real
  S3-compatible interface until the artifact sprint.
- Extraction criteria (later): a module needs independent scaling or a
  different security domain.
