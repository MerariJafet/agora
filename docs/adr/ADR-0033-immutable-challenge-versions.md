# ADR-0033: Immutable Challenge Versions and Frozen Scoring

Status: Accepted

Challenge authors may draft and validate a Challenge, but a
`ChallengeVersion` freezes the verifier manifest, complexity vector and
scoring formula before a `ChallengeInstance` starts. Once frozen, submitted
answers are judged against that exact version.

Sprint 06 exposes no generic update endpoint for ChallengeVersion rows.
Later improvements must create a new ChallengeVersion rather than rewriting
rules after participants have submitted work.

This keeps ScoreEvents recalculable and prevents scoring-rule injection or
retroactive rule changes after seeing submissions.
