# API authorization boundary review — 2026-09-09

Scope: source review of alpha/moderation, artifacts, modules, research-market and research-protocol/institutional routes and their service enforcement. No live writes, DB exploit tests or provider calls were performed by this reviewer. The coordinator owns serial isolated integration execution. These findings are confirmed from complete route-to-service paths; runtime regression validation is recorded separately by the coordinator.

## Findings and implemented corrections

### API-AUTH-01 — HIGH: ordinary devices could perform operational administration

Before correction, `routes/alpha.py` used `CurrentDevice` for feature-flag updates, moderation actions and drills. `CurrentDevice` validates device/session identity and revocation, not administrative authority. `alpha_service.upsert_feature_flag`, `apply_admin_action` and `run_drill` had no authorization checks. The existing alpha tests called a normally registered agent “admin” without granting any privilege.

Impact: agent B could change an existing global flag and its risk classification, or resolve/reject agent A's report. Those tables feed readiness, so an agent could manipulate that operational verdict. The moderation action only changes report status and records an event: this inspection does NOT establish actual device revocation, object quarantine, code execution or token theft. FeatureFlag use found here is operational metadata/readiness; no claim that it bypassed the separate production configuration gates.

Correction: service-level `require_alpha_admin` checks `get_settings().alpha_admin_agent_ids`, default empty (configuration supplied by coordinator). All three privileged service entrypoints deny identities outside the explicit allowlist; no environment bypass. Public report submission remains available to authenticated agents. A valid device session alone no longer authorizes admin writes. Deployment must deliberately assign the operator identity; registration names never grant authority.

Regression: `tests/integration/test_alpha.py` explicitly grants selected test admins through monkeypatch, asserts empty-list denial, then tests agent B cannot change A's flag, resolve a report or create a drill. It verifies protected state and admin action count unchanged.

### API-AUTH-02 — MEDIUM: cross-agent plot runtime modification

Before correction, `modules_service.set_plot_runtime` checked only the runtime enum and changed any supplied plot. The route accepted any `CurrentDevice`. Publish/update/rollback already checked module creator, making runtime modification an inconsistent ownership boundary.

Impact: agent B could set A's semantic plot state to dormant/hot. This is declarative simulated state, not proof of executing or stopping arbitrary code or purchasing compute.

Correction: allow the associated module creator OR the active lease owner, with lease state, plot ID and module ID all matching. Unowned/empty plots are denied. Checks run before mutation and ledger append. Existing schema enums remain enforced.

Regression: `tests/integration/test_modules.py` adds reviewer B runtime denial and verifies the plot remains unchanged, followed by creator A's successful runtime change.

### API-AUTH-03 — HIGH integrity: provisional reward front-running and silent amount mismatch

Before correction, `routes/research_protocol.post_reward_calculation` ignored `_device`; `calculate_reward` accepted any authenticated request's `total_aceros` and persisted the first PROVISIONAL record. Later requests returned that existing record even for a different amount. Thus agent B could choose the first amount for A's candidate, and A could not correct it by a legitimate calculation retry.

Impact: unauthorized persistent provisional allocation and misleading idempotent response. This is NOT an on-chain transfer exploit: institution/reward-lock production gates remain separate and blocked. The requested amount is still a provisional calculation, not verified treasury funding.

Correction: pass caller agent ID, lock candidate row `FOR UPDATE`, require candidate creator before querying existing reward, enforce schema-equivalent integer range (100..1,000,000,000,000) and divisibility by 100, and reject a conflicting existing amount with 409. Same creator/same amount retry returns the existing record. Candidate row locking serializes first calculation/retries.

Regression: `tests/integration/test_research_protocol.py` tests B's front-run rejected before A calculates, same amount/same ID retry, changed amount 409, B retry denial and invalid range/divisibility 422. Existing institution quorum and financial boundary tests remain part of the coordinator's selected suite.

## Alpha readiness scope

The original six checks combine three DB observations with static booleans including `public_deploy_not_performed` and `no_sprint_11`. `GO` is therefore not evidence of OIDC safety, deployment, backup restore, full test passage, institutional accreditation or token release.

Implemented additive fields preserve existing consumers of `status` while declaring:

```json
{"scope":"local_alpha_simulation","production_release_authorized":false}
```

Clients should show the scope adjacent to the status. A future production gate must consume independently verified evidence and should not reinterpret this response as release authorization. The separate release report/fingerprint remains authoritative.

## Inspected positive controls (source evidence, not blanket security approval)

- Artifact publication requires `artifact.created_by_agent_id == device.agent_id` before storage write. Download requires published state and uses attachment/octet-stream/nosniff. Public metadata listing is intentionally public; this review does not infer a private tenant model that is absent from the artifact contract.
- Module update, publication and rollback enforce creator identity in the service. Module manifests are declarative; runtime state does not grant local permissions.
- Research-market proposal submission, information updates and lifecycle actions enforce creator identity; public assessment/review is not equivalent to changing author-owned fields.
- Candidate freeze enforces beneficiary membership and challenge linkage; reused candidate idempotency keys from another agent are rejected.
- Human institutional review checks active institution, exact representative owner and Ed25519 signature bound to the canonical candidate review payload. Institutional activation and reward lock retain the explicit production prohibition.
- Synthetic assignments check assigned validator identity; the pilot remains a test-only path and does not satisfy human validation.

## Validation and remaining limits

Executed by this reviewer: targeted Ruff over the changed source/test files, `git diff --check`; both passed. No integration success is claimed here before the coordinator executes the isolated suite. No confirmed CRITICAL exploit was established in this bounded review; the three narrower findings above are actionable without inventing broader impacts. Public moderation text/evidence references require a documented public-data policy, but this review did not demonstrate confidential data exposure or classify every public GET as IDOR.

Files changed: `apps/api/agora_api/alpha_service.py`, `modules_service.py`, `research_protocol_service.py`, `routes/research_protocol.py`; `tests/integration/test_alpha.py`, `test_modules.py`, `test_research_protocol.py`. Existing privileged success fixtures in `tests/security/test_public_alpha_hardening.py` and `tests/e2e/test_public_alpha_gate.py` were updated to explicitly authorize their admins. Configuration field is owned by the coordinator. No live admin identity was granted or live agent state changed.
