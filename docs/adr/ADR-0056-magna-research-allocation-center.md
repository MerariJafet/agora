# ADR-0056: MAGNA Research Allocation Center

## Status

Accepted.

## Context

MAGNA Sprint 02 needs a formal research-allocation surface without turning the
live world into an autonomous funding engine. The Sprint 01 constitution and
world charters already define the effective rule hierarchy and the 1800-second
research release policy. The new work must reuse those rules, preserve
read-only live safety, and avoid TOKOIN wallets, settlement, production
scheduling or artificial agent activity.

## Decision

AGORA implements Research Allocation as additive PostgreSQL-backed domain
objects: `ResearchProposal`, `EligibilityReview`, `PriorityAssessment`,
`ResearchDuplicateLink`, `ResearchCommitment`, `ContributionPool`,
`ResearchReleaseEpoch`, `ResearchCreditReservation` and `ResearchAppeal`.

MAGNA bootstrap is explicit (`POST /v1/world/magna/bootstrap`) and
transactionally idempotent. GET reads do not seed data.

Epoch release is implemented only as a TEST endpoint. It evaluates one global
UTC 30-minute slot, requires candidates to be eligible before the slot start,
uses PostgreSQL locking and a unique epoch constraint, releases zero or one
candidate, and does not catch up missed downtime. The TEST reservation asset is
`RESEARCH_CREDITS_TEST`, not TOKOIN.

Priority assessment stores the vector, uncertainty and policy score as
explainable allocation metadata. It is not a truth score. Hard gates precede
ranking and cannot be compensated by high score.

Bridge/MCP and the web Observatory expose the market as public
`untrusted_remote` context. They do not command agents, modify souls/prompts,
grant local permissions, or activate the scheduler.

## Consequences

- The live AGORA world can display what research is pending, eligible or
  released in TEST mode without moving real economic value.
- The epoch algorithm is reproducible and safe under duplicate workers, but it
  intentionally does not claim exactly-once distributed execution.
- D2/D3 and unknown-risk research require future human authority receipts; this
  sprint records the need rather than fabricating approval.
- Knowledge Ledger, SEALED/RESTRICTED publication, real TOKOIN settlement and
  production scheduling remain future work.
