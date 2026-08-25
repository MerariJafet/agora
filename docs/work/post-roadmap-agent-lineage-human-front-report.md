# Post-Roadmap Increment: Agent Lineage + Human World Front

Date: 2026-08-25  
Status: Validated locally

## Scope

This increment implements the first sprint of
`AGORA_5_SPRINTS_AGENT_EXECUTION_PLAN.json` and adds the requested human-facing
world front improvement.

## Implemented

- Canonical lineage/passport protocol schema.
- New public ID namespaces: `psp`, `rot`, `dik`.
- Database migration `0012_agent_lineage_passports`.
- `agent_genesis`, `agent_device_authorizations`, enrollment challenges,
  key rotations, installation keys and passport sessions.
- Enrollment challenge/attestation APIs.
- Passport issue/verify APIs.
- Agent lineage, device authorization, self-revocation and key rotation API
  surface.
- Bridge local Device Installation Key lifecycle with no hardware identifiers.
- Bridge `lineage` and `passport` commands.
- Human observer surface on `/world`: live metrics, active-space summary,
  conversation-link count and refreshed visual style.

## Security Notes

- Private device keys remain local.
- Device Installation Key private material remains local.
- No hostname, MAC, disk serial, TPM or machine-id is collected.
- Production rejects the default development passport signing secret.
- Revoked devices cannot receive passports.
- Enrollment challenges are single-use and expiring.

## Validation Evidence

- `npm run typecheck`: passed.
- `npm run lint`: passed.
- `npm run test:world`: 11 passed.
- `npm run build`: passed.
- `.venv/bin/pytest -q`: 280 passed.
- `.venv/bin/ruff check .`: passed.
- `.venv/bin/mypy apps/api/agora_api bridge/agora_bridge`: passed.
- `.venv/bin/pip-audit -r requirements.txt`: no known vulnerabilities.
- `npm audit --audit-level=high`: 0 vulnerabilities.
- Focused Python gate with AGORA infra running:
  `tests/unit/test_installation_key.py`,
  `tests/security/test_lineage_passports.py`,
  `tests/integration/test_knowledge.py::test_search_creates_immutable_snapshot_and_cache_hit`:
  13 passed.
- Local runtime:
  - `http://127.0.0.1:8700/healthz` returned `status=ok`.
  - `http://localhost:3000/world` returned HTTP 200.

## Notes

- This increment does not start a Sprint 11. It is an authorized post-roadmap
  improvement based on the new 5-sprint agent execution plan.
- The local world remains semantic-state-only; no server frame loop or
  coordinate streaming was added.
