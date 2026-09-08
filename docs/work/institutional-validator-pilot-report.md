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
- Reviews, findings and reproductions enter the Knowledge Genealogy append-only.
- Synthetic approval cannot satisfy human quorum or settle TOKOIN.

## Local Pilot Profiles

- `/home/merari-acero/.agora-agents/universidad-codex-test`
- `/home/merari-acero/.agora-agents/universidad-claude-test`

The profiles use separate folders, memory boundaries and read-only CLI brains.
They have no local permissions and must be registered and independently
activated before assignment.

The resumable operator is `scripts/institutional_validator_pilot.py`. Its
`register`, `bootstrap`, `review`, and `status` stages preserve sealed drafts
between retries. A provider authentication failure cannot generate a review,
commitment, reveal, human-validation signal, or TOKOIN movement.

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
