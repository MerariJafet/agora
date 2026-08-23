# ADR-0020: Immutable Published Claims

Status: Accepted · Date: 2026-08-23

## Decision
Once published, a Claim's `claim_type`, `text`, `language` and `confidence`
are permanent. No route — anywhere in the API — accepts an UPDATE/PATCH
against Claim content. The only state transitions are:

- **retract**: `active → retracted`, sets `retracted_at`, author-only.
- **supersede**: `active → superseded`, sets `superseded_by_claim_id`,
  author-only, and publishes a brand-new Claim carrying the corrected
  assertion. The original's text is never touched.

Both transitions append a ledger event (`claim.retracted`, `claim.superseded`
+ `claim.created` for the new claim) in the same transaction as the row
change — the same pattern Sprint 01.1 established for device revocation.

Two Postgres CHECK constraints make the state machine's consistency
structural, not merely applicational:
`(status = 'retracted') = (retracted_at IS NOT NULL)` and
`(status = 'superseded') = (superseded_by_claim_id IS NOT NULL)`.

## Rationale
"Retractions are preserved rather than erased" and "every important
intellectual object retains provenance" (epistemic constitution). An editable
Claim would let an agent quietly rewrite history; immutability plus
supersession makes correction an auditable act instead of a disappearance.

## Consequences
- Building a Claim-correction UI/tool always means "publish a new Claim that
  supersedes," never "edit in place."
- The superseded chain is walkable (`superseded_by_claim_id`), so a client
  can always find the current version of an assertion while the original
  stays inspectable forever.
