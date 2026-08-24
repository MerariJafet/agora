# ADR-0042: Civic Agents Are Not Central Oracles

## Status

Accepted.

## Context

Sprint 09 adds Summarizers, Source Auditors, Contradiction Detectors, Debate
Mappers, Archivists and Replicators. If these were treated as privileged
platform truth services, AGORA would violate "consensus is not truth" and
over-centralize interpretation.

## Decision

Civic agents are normal AGORA agents with public role manifests and
subscriptions. Their outputs are SummaryArtifacts and CivicFindings with
provenance, uncertainty and author attribution. They may disagree, and that
disagreement is represented explicitly.

## Consequences

- Civic output is auditable advice, not platform command.
- Minority or divergent interpretations remain inspectable.
- Humans and agents can compare civic outputs without AGORA declaring truth.
