# ADR-0032: Arena Score, Rating, Reputation and Truth Are Separate

Status: Accepted

Sprint 06 introduces competition, but AGORA must not treat winning as being
factually correct in every context. Arena therefore stores separate concepts:

- `ScoreEvent.score_delta`: cumulative competitive points from one judged
  submission.
- `ScoreEvent.rating_delta` and `ArenaRating.rating`: matchmaking skill
  projection.
- `Judgment.correctness`: verifier/judge outcome for a submission.
- audience preference: popularity or clarity perception.
- epistemic reputation: not changed by Arena in Sprint 06.
- truth: never represented as a global score.

The web UI and API return `truth_score: null` and
`epistemic_reputation: null` in leaderboards so clients cannot accidentally
mislabel Arena data as a truth metric.
