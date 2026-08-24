# Sprint 10 Report - Hardening & Public Alpha

Status: DONE locally.

## Implemented

- Public Alpha API for readiness, cost envelope, runbooks, compatibility,
  feature flags, feedback, safe drills and dashboard.
- Moderation report/action workflow with auditable admin actions and no
  reputation mutation.
- Sprint 10 migration `0011_public_alpha`.
- Web `/alpha` gate.
- Integration, security and E2E tests for Sprint 10.
- ADR-0047 through ADR-0050.

## Evidence

- Baseline before editing: `246 passed`.
- Sprint 10 isolated tests:
  `tests/integration/test_alpha.py tests/security/test_public_alpha_hardening.py tests/e2e/test_public_alpha_gate.py`
  -> `16 passed`.
- Full Python regression: `262 passed`.
- Python quality: `ruff check .` passed; `mypy apps/api bridge` passed.
- Frontend quality: `npx tsc --noEmit`, `npx eslint .`, `npm run build` and
  `npm run test:world` passed (`9` frontend tests).
- Security audits: `pip-audit -r requirements.txt` found no known
  vulnerabilities; `npm audit --audit-level=critical` found `0`
  vulnerabilities.
- Fresh DB bootstrap: Alembic migrated a new database to `revision=0011` and
  confirmed `alpha_tables=5`.
- Secret scan: no matches for common private key/API key/token patterns.

## Bug Fixed During Sprint

- `agora claim <code>` failed when a valid claim code began with `-` because
  Click parsed it as an option. The CLI now treats the claim code as
  unprocessed opaque input.

## Final Scope Note

Sprint 10 is the final roadmap sprint. There is no Sprint 11 in the active
roadmap.
