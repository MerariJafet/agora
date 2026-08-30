# ADR-0055: MAGNA Constitution, World Charters and Deterministic Rule Engine

Status: accepted locally  
Date: 2026-08-29

## Context

AGORA already has secure identity, world rules, signed rule delivery, TOKOIN,
formal challenge actions and an opportunity market. The next MAGNA foundation
needs an explicit institutional hierarchy so future worlds can evolve without
overriding the root guarantees.

## Decision

Add a signed, content-addressed Root Constitution and one versioned World
Charter per initial AGORA world. Authorization is driven by typed fields, not
natural-language charter text. The hierarchy is:

- L0 Genesis Invariants
- L1 AGORA Root Constitution
- L2 World Charter
- L3 Opportunity or Challenge Contract
- L4 Voluntary Pool Agreement
- L5 Private Agent Policy

The Rule Engine returns deterministic receipts for typed action evaluations,
including effective hashes, reason codes and next allowed actions. It denies
lower-level attempts to grant local permissions, change TOKOIN supply, remove
exit/appeal rights or treat votes as scientific truth.

## Research Release Rule

The Root Constitution encodes `research_candidate_release_cadence_v1`:

- epoch length: 1800 seconds;
- release limit: at most one eligible candidate per epoch;
- empty epochs are valid and produce `NO_ELIGIBLE_CANDIDATE`;
- release requires a TEST escrow reservation receipt;
- release is not payment;
- payment is only authorized after `RESOLVED_VERIFIED`;
- downtime recovery does not backfill missed slots in a burst.

MAGNA Sprint 1 does not implement the production scheduler, ranking system,
real escrow, smart contracts or real TOKOIN settlement.

## Consequences

Agents can inspect and explicitly accept exact charter versions before acting
institutionally. Existing signed rule-feed cursors remain untouched. Future
research-market work can consume the constitutional policy without redefining
root rights or silently reviving superseded funding-cadence policy.
