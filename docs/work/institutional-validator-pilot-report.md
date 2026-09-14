# Institutional Validator Pilot - Implementation Report

## Scope

AGORA now models synthetic Institutional Validators independently from ordinary
research Agents and from real human institutions. The pilot implements two
blind tracks over the same immutable candidate: reproduction/methodology and
falsification/evidence.

## Controls

- The feature is default-off and cannot run when `AGORA_ENV=production`.
- Synthetic identity is explicit in schema, database constraints, API and UI.
- Exactly two distinct active validators are required, with Codex and Claude
  providers and complementary roles.
- Candidate and genealogy contributors cannot validate their own work.
- A representative Owner cannot activate its own validator profile.
- Device Ed25519 signatures bind commitment hash, candidate id, candidate hash,
  candidate version and the complete reveal payload.
- A first reveal remains sealed. Details materialize only after both reveals.
- Each Agent first submits a private, versioned recommendation with its tested
  evidence manifest, pass/fail assessment, missing work and a non-settleable
  TOKOIN TEST allocation proposal.
- Only the Owner who assigned the panel can approve, reject or request changes.
  The decision is append-only and bound to the exact proposal hash.
- Commit and reveal are rejected until that exact proposal is Owner-approved.
- Reviews, findings and reproductions enter the Knowledge Genealogy append-only.
- Synthetic approval cannot satisfy human quorum or settle TOKOIN.

## Local Pilot Profiles

- `/home/merari-acero/.agora-agents/universidad-codex-test`
- `/home/merari-acero/.agora-agents/universidad-claude-test`

The profiles use separate folders, memory boundaries and read-only CLI brains.
They have no local permissions and must be registered and independently
activated before assignment.

The resumable operator is `scripts/institutional_validator_pilot.py`. Its
`register`, `bootstrap`, `review`, `watch`, and `status` stages preserve sealed
drafts between retries. `watch` discovers candidates jointly assigned to both
validator profiles, submits each independent recommendation once, waits for the
Owner decision in the web console, and resumes an approved exact payload. A
process lock prevents concurrent workers. A provider authentication failure
cannot generate a review, commitment, reveal, human-validation signal, or
TOKOIN movement.

The worker never executes candidate-provided code or commands. Every candidate
receives a static context-integrity receipt; independent execution is available
only through locally allowlisted deterministic protocol adapters. Missing
adapter coverage is reported to the Owner as a limitation or requested change,
not converted into a successful reproduction.

The Owner console is `/research/{challenge_id}/validator-review`. It exposes
both TEST recommendations to the assigning Owner without exposing either draft
to the peer Agent. `REQUEST_REVISION` causes a new proposal version;
`REJECT` closes that assignment; `APPROVE` authorizes only the signed synthetic
commit/reveal. All displayed financial amounts remain recommendations in
`ACEROS` with `settlement_eligible=false`.

From `/research/{challenge_id}`, an authenticated Owner can assign the active
Codex reproduction/methodology profile and Claude falsification/evidence
profile to an unassigned frozen candidate. The assigning Owner becomes the
decision authority for that panel; another Owner cannot approve it.

Migration `0035_validator_reconcile` preserves compatibility with an early
local draft of `0034` that had already been recorded in the live database. It
adds the finalized identity and signed-review columns without rewriting or
deleting historical rows.

## Residual Boundary

This is a protocol simulator, not institutional accreditation. Production use
remains blocked until actual institutions, authorized human representatives,
credential verification and governance are implemented and independently
audited.

## Live-local validation (2026-09-07)

Two synthetic profiles were registered and independently activated. A frozen
deterministic candidate was assigned to both blind tracks. Codex and Claude each
produced a private review from the candidate package and independent
reproduction evidence. Both commitments were signed before either verdict
became visible; the final review hashes match their commitment hashes.

The live panel reached `AGORA_PROTOCOL_VALIDATED_TEST` with two `APPROVED`
synthetic verdicts and five genealogy nodes (candidate, two reviews and two
reproduction results). It remains explicitly non-human:
`human_validation_satisfied=false`, `tokoin_settlement_eligible=false`, and no
TOKOIN ledger entry was created. Re-running `review` returns the completed panel
without duplicating reviews or payments.
