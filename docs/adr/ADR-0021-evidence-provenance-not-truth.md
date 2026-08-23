# ADR-0021: Evidence Is Provenance, Not Truth

Status: Accepted · Date: 2026-08-23

## Decision
Evidence is inert metadata describing where a claim's support supposedly
comes from — it is never independently verified by AGORA in Sprint 04.
Three `provenance_level` values exist:

- `reference_only` — a bare pointer; AGORA has not looked at the content.
- `client_hashed_snapshot` — the submitting client recorded a sha256 of
  content it personally observed. This describes what the CLIENT saw, not
  what AGORA verified.
- `agora_verified_snapshot` — reserved for a future trusted Knowledge Fabric
  adapter. **No client-facing API path can produce this value**: every write
  path (`create_evidence`, atomic evidence-at-claim-creation) calls
  `_guard_provenance()`, which rejects it outright regardless of what the
  JSON Schema's enum alone would allow. This is defense in depth — the DB
  CHECK constrains the enum, the application guards who may assert which
  member of it.

`locator`, `title`, `excerpt` and `publisher` are stored exactly as
submitted and are never dereferenced (see ADR-0024). Excerpts are bounded to
600 characters — a quotation, never a copied document.

## Rationale
"Evidence count is not evidence quality" and "author confidence is not
certified probability" (epistemic constitution). Treating unverified
metadata as verification would let volume of citation substitute for
correctness — the opposite of what a debate-quality signal should reward.

## Consequences
- The web UI must always render provenance level honestly ("reference only —
  not independently checked by AGORA") rather than a generic checkmark.
- When Knowledge Fabric ships a real adapter, `agora_verified_snapshot`
  becomes reachable ONLY from that adapter's own privileged write path — the
  client-facing guard in this ADR is not touched.
