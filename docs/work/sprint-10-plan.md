# Sprint 10 Plan - Hardening & Public Alpha

Sprint 10 is the final roadmap sprint. It does not add a new product category;
it turns the Sprint 01-09 platform into an operable local Public Alpha gate.

## Scope

- Public Alpha operational API: readiness, cost envelope, runbooks, threat
  boundaries, feature flags, feedback and safe drills.
- Moderation workflow: report, quarantine, suspend, revoke, appeal, review,
  reject and resolve. Admin actions are auditable and do not mutate scientific
  reputation.
- Safe local chaos/load drills: deterministic records for Postgres, Redis,
  NATS, outbox, object-store, Knowledge outage, backup/restore and 10k
  synthetic realtime. No external deploy or credential is touched.
- Web shell: `/alpha` shows gate status, costs, moderation, flags, runbooks,
  protocol compatibility and reviewed boundaries.
- Tests: integration, security and E2E coverage for the Public Alpha gate.

## Non-scope

- No public deployment.
- No Sprint 11.
- No external credentials.
- No Arena Points changes, ranking changes or Knowledge providers.
- No automatic artifact/module execution.

## Validation Order

1. Run existing baseline before editing.
2. Add schema, models, migration and service.
3. Add API routes and web page.
4. Add Sprint 10 tests.
5. Update docs/ADRs.
6. Run isolated tests, full Python suite, frontend gates, audits and fresh
   migration bootstrap.
