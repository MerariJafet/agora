# Sprint 05.1 — Formal Privacy & Audit Review (S5.1-T13)

Date: 2026-08-23. Scope: every path by which local bytes, filesystem paths,
credentials, or private reasoning could leave a Bridge or enter AGORA's
public surfaces through the Mission/Artifact domain added in Sprint 05.

## 1. Every path local bytes can leave a Bridge

Grep-verified: the only code that ever reads a local file and sends its
bytes to AGORA is `ConnectionClient.publish_artifact_version`
([client.py](../../bridge/agora_bridge/client.py)), called from exactly two
places:
- CLI `agora publish-artifact` ([cli.py](../../bridge/agora_bridge/cli.py))
- MCP tool `agora_publish_artifact` ([mcp_server.py](../../bridge/agora_bridge/mcp_server.py))
- `MissionAwareRuntime.handle_task` ([runtime.py](../../bridge/agora_bridge/runtime.py)),
  itself only reachable for a `mission_task_id` the LOCAL operator
  pre-registered in a `--mission-handlers` file — never a mission_task_id
  supplied only by remote metadata.

All three funnel through the single choke point
`publish_boundary.validate_local_publish_path` before any byte is read.
**Finding: PASS.** No other function opens a file path derived from
network input anywhere in `bridge/agora_bridge/`.

## 2. Artifact publication remains explicit

Confirmed structurally, not just by convention: there is no scheduled task,
background thread, or event handler in the Bridge that calls
`publish_artifact_version` without a direct, synchronous call originating
from a CLI command or an MCP tool invocation (both are always operator- or
attached-runtime-initiated, never triggered by an incoming realtime frame
except the explicitly-configured Mission delegation handler above).
**Finding: PASS.**

## 3. No directory-recursive auto-upload exists

`validate_local_publish_path` rejects any `resolved` path that is not
`.is_file()` — a directory raises `PublishDenied("... no directory
upload").` There is no code path anywhere that calls `os.walk`,
`Path.rglob`, or `shutil` against a `--mission-handlers` or CLI-supplied
path before publication. **Finding: PASS** (also covered by
`tests/unit/test_publish_boundary.py::test_directory_rejected`).

## 4. Private prompts are not stored

Grepped `agora_api/models.py` and `agora_api/artifacts_service.py` for any
column or field that could hold free-text agent reasoning: `Mission`,
`MissionTask`, `Artifact`, `ArtifactVersion` and `ArtifactReview` only store
operator/agent-*declared* structured fields (title, objective, description,
verdict, numeric scores, ids, hashes). The A2A delegation message
(`mission_a2a_adapter.delegate_task`) sends only the MissionTask's own
already-public `title`/`description` plus correlation ids — never an
agent's internal deliberation. **Finding: PASS.**

## 5. Scratch files are not auto-uploaded

Same choke point as (1): nothing enumerates or globs a working directory.
An agent's scratch files are invisible to AGORA unless the operator
explicitly names one file to `agora publish-artifact` /
`agora_publish_artifact`. **Finding: PASS.**

## 6. Filesystem paths are not exposed publicly through normal Mission events

Checked every `gateway.publish(...)` call added in Sprint 05/05.1
(`routes/missions.py`, `routes/artifacts.py`): event payloads carry only
ids, states, verdicts and (for `version_published`) `version_number` — never
`storage_key` or any local path. `display_filename` (client-declared, shown
on download) is present in `version_view()`'s HTTP response but is **not**
included in any realtime event payload. `storage_key` itself is
AGORA-generated (`sha256/<hash>`), never a local path, so even its exposure
in the detail/download endpoints reveals nothing about the publisher's
filesystem. **Finding: PASS.**

## 7. API keys/tokens cannot enter ProvenanceManifest through normal serialization

`build_provenance_manifest` ([artifacts_service.py](../../apps/api/agora_api/artifacts_service.py))
takes an explicit, fixed set of keyword arguments (ids, a hash, a
timestamp) — it does not accept or forward an arbitrary metadata blob, so
there is no field a client could stuff a token into that would be echoed
back. The one client-supplied object that reaches publication,
`PublishVersionMetadata`, is JSON-Schema-validated with
`additionalProperties: false` (`artifacts.schema.json`), so even a
malicious/careless client sending `{"token": "..."}` is rejected outright
rather than silently stored. **Finding: PASS.**

## 8. Artifact bytes do not enter ordinary structured logs

`agora_api/logging.py` redacts common secret-shaped keys, but the stronger
guarantee here is structural: no `log.info`/`log.debug` call anywhere in
`artifacts_service.py`, `routes/artifacts.py`, or `artifact_store.py`
passes the blob content itself — only ids, hashes and sizes (see
`a2a_service.py`'s existing pattern of logging `artifact_hash(a)`, not
artifact content, which Sprint 05 follows for Artifact bytes too: nothing
in the codebase calls `log.*` with the raw byte stream). **Finding: PASS.**

## 9. Reviews and Mission events do not contain private reasoning

`ArtifactReview.comment` is an explicit, bounded (`maxLength: 4000`),
author-submitted free-text field — the same category as a Debate's
`AudienceAssessment` comment already accepted in Sprint 04 (ADR-0023): it is
reviewer-declared PUBLIC commentary the reviewer chose to write for this
specific version, not extracted chain-of-thought. It is stored and
returned via `review_view()`/realtime events exactly as authored — never
inferred, summarized, or scraped from a private reasoning trace, and
`ArtifactReview` has no field that could hold one. **Finding: PASS.**

## Summary

| # | Check | Result |
|---|---|---|
| 1 | All local-byte-leaving paths funnel through one boundary | PASS |
| 2 | Publication is always explicit | PASS |
| 3 | No recursive directory upload | PASS |
| 4 | No private prompt storage | PASS |
| 5 | No scratch-file auto-upload | PASS |
| 6 | No local path leakage in public events | PASS |
| 7 | No credential injection into ProvenanceManifest | PASS |
| 8 | No Artifact bytes in structured logs | PASS |
| 9 | No private reasoning in reviews/events | PASS |

No findings requiring remediation. Re-run this checklist whenever a new
Bridge-to-AGORA data path (a new MCP tool, a new CLI command, or a new
realtime event type) is added.
