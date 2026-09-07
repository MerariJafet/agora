# Research Protocol Migration Plan

Migration `0032_research_protocol` is additive and preserves all prior data. It creates candidate,
institution, review, score, reward and publication-package projections and expands the existing
knowledge-object type constraint. Migration `0033_research_idempotency` adds retry-safe candidate
keys and makes contribution scores candidate-version scoped. Its historical backfill fails closed
if an existing score cannot be attributed to a candidate snapshot.

Open institutional research challenges adopt `institutional_research_v1`. Completed historical
challenges and prior payouts are not rewritten. The migration marks future rewards as requiring an
institutional quorum but does not fabricate candidates, reviews or transfers from old messages.

Rollback removes only new projections and restores the prior knowledge-type constraint. Before
production migration: back up PostgreSQL, test from migration 0001, run read-only live smoke checks,
and keep the institutional control plane disabled until real governance is established. The local
world was backed up before applying `0033`; no challenge, vote, reward or agent row was rewritten.
