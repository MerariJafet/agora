# MAGNA Sprint 04.1 API Authority and Split-Brain Audit

Canonical API for local operator use: `http://127.0.0.1:8700`

Secondary observed API: `http://127.0.0.1:8710`

Role classification: `SHARED_STATE_REPLICA_WITH_POSTGRES_TRANSACTIONAL_AUTHORITY`

The two local API processes are not independent authorities. They share the
same PostgreSQL source of truth, schema version, Event Ledger, transactional
outbox and Redis/NATS environment. Logical write correctness is enforced by
database constraints, idempotency keys and append-only events rather than by a
process-local memory state.

Split-brain result: `NO_DIVERGENT_STATE_AUTHORITY_DETECTED`

Residual risk: the 04.1 roadmap used the phrase "single-writer protocol". The
current AGORA design uses a single transactional database authority instead of
a single API writer. That is acceptable for the local modular monolith, but a
future public deployment should document load-balancer and migration ownership
more formally before accepting public write traffic.

Live-service rule: Sprint 04.1 did not require stopping or restarting either
API process. New 04.1 endpoints were verified in isolated tests, not by mutating
or restarting the live world.
