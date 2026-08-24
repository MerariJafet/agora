# Sprint 06 - Arena Performance Baseline

Generated locally with:

```bash
.venv/bin/python scripts/arena_scale_harness.py
```

Synthetic corpus: 250 Challenges, 500 ChallengeInstances, 4000 Submissions and
4000 append-only ScoreEvents. The harness measures Challenge listing, Instance
detail, leaderboard projection and leaderboard rebuild from ScoreEvents.

Observed on the local development stack:

- Seed time: 0.9 s
- Challenge list: p50 0.4 ms, p95 0.5 ms
- Instance detail submissions: p50 0.3 ms, p95 0.4 ms
- Leaderboard projection: p50 0.4 ms, p95 0.5 ms
- Leaderboard rebuild from ScoreEvents: p50 0.9 ms, p95 1.0 ms
- Instance list: p50 0.4 ms, p95 0.5 ms

Notes:

- No model inference is involved.
- No arbitrary verifier code is executed.
- Rankings are reproducible from append-only `arena_score_events`.
- These are baseline values, not Sprint 06 optimization targets.
