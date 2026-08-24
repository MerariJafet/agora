# ADR-0047: Public Alpha Operational Gates

Status: Accepted

AGORA Public Alpha readiness is represented as explicit checks: open critical
moderation, outbox backlog, high-risk feature flags, no secret requirement, no
public deploy and no Sprint 11. The gate is inspectable by API and web UI.

This is not a deployment system. It reports readiness and records local drills
without touching external infrastructure.
