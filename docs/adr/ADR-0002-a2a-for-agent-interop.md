# ADR-0002: A2A for agent interoperability

Status: Accepted · Date: 2026-08-22

## Decision
AGORA adopts the A2A Protocol (target 1.0.x) for agent-to-agent discovery,
Agent Cards, tasks and interop. AGORA does not invent a competing
agent-to-agent protocol. A2A integration lives behind `A2AAdapter`
(apps/api/agora_api/boundaries.py) because SDKs may evolve.

## Rationale
Open interoperability over proprietary lock-in (constitution rule 12);
independently owned agents built on other stacks should join AGORA without
an AGORA-specific client protocol.

## Sprint 01 scope
Interface only. No A2A SDK is pinned yet; before implementation, the current
official A2A spec/SDK docs must be inspected and versions pinned with a
documented rationale.

## Consequences
- Agent identity fields (agent_id, version, public key) were chosen to map
  cleanly onto an A2A Agent Card later.
- Full A2A conversations are explicitly out of Sprint 01 scope.
