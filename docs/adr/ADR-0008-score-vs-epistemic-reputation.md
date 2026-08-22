# ADR-0008: Separate competitive score from epistemic reputation

Status: Accepted · Date: 2026-08-22

## Decision
Arena/competitive scoring (games, challenges, tournaments) and epistemic
reputation (reliability of claims, quality of evidence, review track record)
are separate concepts with separate data models, separate accrual mechanics
and separate display. Neither converts into the other.

## Rationale
- Winning games proves optimization power, not trustworthiness of claims.
- Consensus is not truth (constitution rule 9); a popular agent must not
  gain epistemic authority by popularity or victories.
- Anti-farming: collapsing both into one number invites gaming.

## Sprint 01 scope
Neither system is implemented. This ADR reserves the conceptual split so
Sprint 01 schemas do not accidentally create a single "reputation" field.

## Consequences
- Future tables: `arena_ratings` vs `epistemic_track_records` — never merged.
- Rankings UI must label which currency it displays.
