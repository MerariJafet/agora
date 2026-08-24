# Sprint 10 Load and Chaos Baseline

Environment: local development stack, no LLM inference, no external deployment.

## Synthetic Baselines

- Realtime 10k synthetic: recorded via `/v1/alpha/drills` with
  `target_connections=10000`, `llm_calls=0`, and no public ports.
- NATS/Redis/Postgres/object-store outages: recorded as safe simulations with
  `destructive_actions=false` and `external_services_touched=false`.
- Outbox redelivery: covered by historical durable dedup and Sprint 10 drill
  record; at-least-once delivery remains the contract.

## Honest Limit

The local gate validates control-plane readiness and arithmetic for 10k
connections. It does not claim production throughput because no public staging
deployment was authorized.

## Backup/Restore

Fresh bootstrap is validated by creating a clean database, migrating Alembic
from base to head and confirming the Sprint 10 alpha tables exist.
