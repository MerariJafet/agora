# ADR-0025: Debate Competition Deferred to Arena

Status: Accepted · Date: 2026-08-23

## Decision
Sprint 04's Debate is pure structure: capped participants, named positions,
Claims, Evidence, an argument graph, and audience perception capture. It
computes no winner, no score, no ranking, no Elo/Glicko/TrueSkill rating, no
Arena Points, no tournament bracket, and no "difficulty" measure. Closing a
Debate freezes assessments — it does not crown anyone.

This mirrors ADR-0008 (Sprint 01: "Separate Competitive Score from Epistemic
Reputation") one level down: within a single Debate, structure and
perception-capture are themselves separate from competition, which does not
exist yet at all.

## Rationale
The sprint's own constraints are explicit: "Do not create Arena Points or
competitive rankings in this sprint," "Do not declare a debate winner based
only on audience popularity." Building scoring now — even a "simple" one —
would encode assumptions (what counts as winning an argument? by what
metric?) that belong to a dedicated Arena design with its own anti-farming
and fairness considerations, not a byproduct of the Claims/Debates data
model.

## What Arena will need from this foundation (forward compatibility)
When an Arena sprint arrives, it can build on Sprint 04 objects without
touching them:
- `Debate.status == "closed"` is already the natural trigger point for any
  future scoring pass.
- `AudienceAssessment` rows are preserved forever (frozen, not deleted) —
  Arena could read them as one input among several, but must not treat them
  as the score itself (ADR-0023 still applies).
- `ClaimRelation` and Evidence attachment structure already give Arena a
  substrate to evaluate argument quality from, if it chooses to, without
  Sprint 04 needing to anticipate the exact algorithm.

## Consequences
- No `winner_position_id`, `score`, or `rating` column exists on `debates` —
  adding one later is an additive migration, not a breaking change to this
  sprint's schema.
- Tests (`test_no_truth_score_or_winner_anywhere`) act as a regression guard:
  if a future change accidentally reintroduces scoring into this domain, the
  test fails immediately.
