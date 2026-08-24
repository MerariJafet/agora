# ADR-0045: Reputation Is Multidimensional

## Status

Accepted.

## Context

A single karma or global trust score would collapse unrelated dimensions and
could silence minority claims. Competitive points, epistemic reputation and
truth must remain separate.

## Decision

Sprint 09 stores append-only ReputationEvents by dimension: Reliability,
Evidence Quality, Calibration, Replicability, Collaboration, Originality,
Critical Analysis, Domain Expertise and Peer Review Quality. Each event keeps
context and sample size. Aggregates expose per-dimension summaries only.

## Consequences

- No universal reputation score exists.
- No truth score exists.
- Future reputation recalculation can replay events with context/sample size.
