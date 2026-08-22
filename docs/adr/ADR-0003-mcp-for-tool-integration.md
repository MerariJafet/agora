# ADR-0003: MCP for tool integration

Status: Accepted · Date: 2026-08-22

## Decision
Agent-to-tool and agent-to-context integration uses MCP (target spec revision
2026-07-28), treated as stateless at the protocol core for that revision.
MCP integration lives behind `MCPAdapter` on the cloud side and, in future
sprints, behind the Bridge's local tool host on the edge side.

## Rationale
Same interoperability principle as ADR-0002. Tools run at the edge (ADR-0001);
MCP is the standard seam for exposing them to the local agent.

## Sprint 01 scope
Interface only; no MCP SDK pinned yet. Version verification against official
docs is required before the first real integration.

## Consequences
- Local tool permissions are governed by the LocalPolicyEngine (ADR-0006) —
  an MCP server's availability never implies permission.
- Remote AGORA content can suggest tool use but never authorize it (SEC-002).
