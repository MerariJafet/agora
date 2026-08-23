# ADR-0028: Content-Addressed, Filesystem-Backed ArtifactStore (Local, Not S3)

Status: Accepted · Date: 2026-08-23

## Decision
`ArtifactStore` is a small vendor-neutral Protocol
(`put_stream` / `open_stream` / `stat` / `verify`). Sprint 05 ships exactly
one implementation, `LocalArtifactStore`: bytes land under
`{root}/sha256/<hash[:2]>/<hash>`, computed incrementally while streaming
(never fully buffered), with a quarantine-then-atomic-rename write path
(`os.replace`, same filesystem) so a crash mid-upload leaves an orphaned
temp file in `_quarantine/`, never a half-written "final" blob. Identical
bytes published twice dedupe to the same file (content addressing gives
this for free).

An `ArtifactVersion` row is immutable from the moment it is inserted:
`content_hash`, `content_size`, `storage_key`, and `provenance_manifest`/
`provenance_hash` are set once at publish time and never updated. There is
no code path that mutates a published version's bytes or metadata — a
correction is always a *new* version (S5-T18's revision loop), never an
edit.

## Rationale
No S3-compatible object store or MinIO sidecar was introduced this sprint.
`boto3` is available (verified: 1.43.78) but was deliberately not adopted:
- No paid cloud credential is required by anything in Sprint 05's mandatory
  scope, and the sprint brief's "if practical" qualifier on ArtifactStore
  design explicitly permits the simpler option when nothing forces the
  heavier one.
- Same posture already accepted twice before: ADR-0022 (PostgreSQL over a
  graph database) and the Sprint 03 dependency-free SVG renderer — "do not
  introduce infrastructure without demonstrated need."
- A filesystem store still fully satisfies every Sprint 05 security
  invariant (streaming hash, byte cap, quarantine, content addressing,
  path-traversal-safe resolution in `_safe_resolve`) without adding a
  second infrastructure dependency to run, back up, and secure.

## Consequences
- `ArtifactStore` is a Protocol specifically so a future S3-compatible
  adapter (MinIO, real S3) can be added later without any caller — routes,
  services, MCP tools — changing. That is the trigger to revisit this
  decision: a real requirement for durability/replication beyond a single
  filesystem, or a deployment target where local disk isn't viable.
- Multi-instance API deployment is out of scope until that adapter exists,
  since `LocalArtifactStore` assumes one shared filesystem root.
