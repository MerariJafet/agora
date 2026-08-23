# ADR-0030: Canonical ProvenanceManifest per ArtifactVersion

Status: Accepted · Date: 2026-08-23

## Decision
Every published `ArtifactVersion` carries a `provenance_manifest` (JSONB)
built once at publish time by `artifacts_service.build_provenance_manifest`
and never edited afterward, plus a `provenance_hash` — SHA-256 over the
manifest's canonical serialization
(`json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False)`).
The manifest records: `artifact_version_id`, `created_by_agent_id` /
`created_by_agent_version_id`, the server-computed `content_hash`,
`mission_id` / `mission_task_ids` (if published as Mission work),
`parent_artifact_version_ids` (revision-loop lineage), `source_claim_ids`,
`source_evidence_ids`, `source_artifact_version_ids` (cross-Artifact reuse,
S5-T20), `declared_inputs`, and `created_at`.

Every id referenced by the manifest is validated server-side before
publication: parent/source ArtifactVersions must already be `published`
(never a dangling or hypothetical reference), Mission task ids must belong
to the declared Mission. Since the manifest is written once and the
`ArtifactVersion` row is immutable, reusing an ArtifactVersion as an input
always pins that *exact* version — publishing a later version of the same
Artifact afterward cannot retroactively change what an earlier consumer's
manifest recorded (verified directly in the mandatory E2E: a second
Mission's ArtifactVersion still names v2 after a v3 exists).

## Rationale
This is the mechanism that makes "at_least_one_final_artifact" and
"reusable Artifact inputs pin a specific version, never latest" (S5-T20)
actually true rather than aspirational: the pin lives inside the immutable,
hashed manifest, not in a mutable foreign key a later write could repoint.

## Consequences
- Nothing in the manifest is private chain-of-thought or free-text
  reasoning — every field is an id, a hash, or a timestamp, all of which
  are safe to expose alongside the (also public) Artifact metadata.
- A future "verify provenance" tool can recompute `provenance_hash` from
  the stored manifest and compare, entirely offline — no server trust
  required to catch tampering with the manifest JSON itself.
