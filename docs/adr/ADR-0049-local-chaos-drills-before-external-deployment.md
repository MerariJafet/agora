# ADR-0049: Local Chaos Drills Before External Deployment

Status: Accepted

Sprint 10 records deterministic local chaos/load drills for Postgres, Redis,
NATS, outbox, object-store, Knowledge outages, backup/restore and synthetic
10k realtime. The purpose is operational evidence before any future staging or
production exposure.

Drills are explicitly safe simulations: no destructive actions, no external
services and no public ports.
