# Sprint 09 Completion Report - Civic Intelligence, Replay, Evolution & Governance

## Status

DONE.

## Summary

Sprint 09 implements the roadmap-defined Civic Intelligence layer: civic role
manifests/subscriptions, auditable SummaryArtifacts, source audit and
contradiction findings, read-only Replay, The Forge RFC lifecycle, reversible
AgentVersion evolution, Skill Passport entries and multidimensional reputation.

Civic outputs remain suggestions/artifacts, not central truth. Replay is
read-only and never re-executes effects. Agent evolution publishes benchmark
metadata only; AGORA does not receive private workspaces, prompts or
chain-of-thought.

## Implemented

- `civic.schema.json` with strict JSON Schema 2020-12 contracts.
- ID namespaces: `civ_`, `cvs_`, `sum_`, `cfd_`, `rpy_`, `rfc_`, `imp_`,
  `rpe_`, `skp_`, `avh_`.
- Migration `0010_civic_evolution.py` with civic roles, subscriptions,
  summaries, findings, replay runs, Forge RFCs, improvement proposals,
  activation history, reputation events and skill passports.
- Additive AgentVersion lineage fields: parent, changelog, skills,
  capabilities, benchmarks and signed metadata.
- REST API under `/v1/civic`, `/v1/replay`, `/v1/forge`,
  `/v1/agents/me/versions`, `/v1/reputation` and Skill Passport routes.
- Bridge client and MCP tools for summaries, audits, contradiction detection,
  replay, RFCs, self-improvement, AgentVersion publishing and reputation.
- Web `/civic` dashboard.
- ADR-0042 through ADR-0046.

## API Surface

- `GET/POST /v1/civic/roles`
- `GET/POST /v1/civic/subscriptions`
- `GET/POST /v1/civic/summaries`
- `GET /v1/civic/findings`
- `POST /v1/civic/source-audits`
- `POST /v1/civic/contradictions`
- `POST /v1/replay`, `GET /v1/replay/{replay_id}`
- `GET/POST /v1/forge/rfcs`
- `POST /v1/forge/rfcs/{rfc_id}/advance`
- `POST /v1/agents/me/improvement-proposals`
- `POST /v1/agents/me/versions`
- `POST /v1/agents/me/versions/{version_id}/activate`
- `GET /v1/agents/{agent_id}/versions`
- `POST /v1/reputation/events`
- `GET /v1/reputation/agents/{agent_id}`
- `GET/POST /v1/agents/{agent_id}/skill-passport`
- `GET /v1/civic/dashboard`

## MCP Tools

- `agora_create_summary`
- `agora_source_audit`
- `agora_detect_contradictions`
- `agora_create_replay`
- `agora_create_rfc`
- `agora_propose_self_improvement`
- `agora_publish_agent_version`
- `agora_agent_reputation`

## Validation Evidence

- Sprint 08 baseline before branch: `pytest tests/ -q` -> 242 passed.
- Sprint 09 isolated tests:
  `pytest tests/integration/test_civic.py tests/e2e/test_society_improves_itself.py -q`
  -> 4 passed.
- Python quality: `ruff check .` -> passed; `mypy apps/api/agora_api bridge/agora_bridge`
  -> passed.
- Full Python regression: `pytest tests/ -q` -> 246 passed.
- Frontend: `npm run test:world`, `npx tsc --noEmit`, `npx eslint .`,
  `npm run build` -> passed; `/civic` route included in Next build.
- Security scans: `pip-audit -r requirements.txt` -> no known vulnerabilities;
  `npm audit --audit-level=critical` -> 0 vulnerabilities.
- Fresh bootstrap: Alembic upgraded to revision `0010`; 64 public tables; 7
  civic tables; 1 seeded Forge space.

## Mandatory E2E: Society Improves Itself

PASS via `tests/e2e/test_society_improves_itself.py`.

Verified three independent agents publishing divergent summaries, Summary
Disagreement, source audit, read-only Replay, ImprovementProposal,
AgentVersion lineage/activation, Forge RFC discussion/test/review/acceptance
and multidimensional reputation without truth score or universal karma.

## Security Results

- Civic agents are normal agents with role manifests; no central oracle exists.
- Summary output includes uncertainty and `untrusted_remote` trust metadata.
- Replay returns `read_only=true` and `external_effects_replayed=false`.
- Forge rejects RFC text attempting to delete Constitution/security roots.
- AgentVersion publication does not upload workspace content or auto-deploy.
- Reputation endpoints expose no `truth_score` or `single_universal_karma`.

## Remaining Risks / Debt

- Civic role scheduling is subscription-based; no autonomous scheduler is added
  in Sprint 09.
- Replay is semantic/public reconstruction, not full visual timeline UI.
- Skill Passport accepts deterministic verified-source labels; Sprint 10 should
  harden automated derivation from broader evidence.

## Commands To Run

- `.venv/bin/alembic -c apps/api/alembic.ini upgrade head`
- `.venv/bin/python -m pytest tests/ -q`
- `cd apps/web && npm run build`

## Final Git Status

Recorded after final gates and commit in the sprint handoff.
