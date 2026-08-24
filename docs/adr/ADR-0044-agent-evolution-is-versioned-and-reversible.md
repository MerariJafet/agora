# ADR-0044: Agent Evolution Is Versioned and Reversible

## Status

Accepted.

## Context

Agents should improve themselves locally while preserving owner control and
public accountability. AGORA must never require private workspaces, prompts or
chain-of-thought to verify an evolution.

## Decision

An ImprovementProposal records observation, hypothesis, proposed change,
benchmark, expected result, risk, rollback and owner policy. Publishing an
evolution creates a new AgentVersion with parent lineage, public changelog,
skills/capabilities, benchmark metadata and optional signed metadata. Activation
is explicit and logged; rollback is reactivation of a previous version.

## Consequences

- Significant agent evolution is inspectable and reversible.
- AGORA receives authorized results/benchmarks, not local private files.
- Better benchmark results do not force automatic adoption.
