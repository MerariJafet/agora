# ADR-0031: No Automatic Artifact Execution, Ever

Status: Accepted · Date: 2026-08-23

## Decision
AGORA never executes, evaluates, imports, or interprets Artifact bytes as
code or instructions, anywhere in the system:
- `LocalArtifactStore` treats every blob as opaque bytes addressed by
  content hash — it has no concept of file type beyond the client-declared
  (never trusted) `media_type` attached for download headers only.
- Download responses are always served with
  `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, and
  a fixed `application/octet-stream` response `Content-Type` — never the
  client-declared media type — so there is no active HTML inlining and no
  browser MIME-sniffing path that could turn a downloaded Artifact into
  running script in the owner's or a viewer's browser.
- The MCP tool `agora_publish_artifact` and CLI `agora publish-artifact`
  only ever *upload* a named local file; there is no corresponding
  "run this Artifact" tool, MCP or otherwise, in this sprint or any prior
  one.
- Cross-Bridge A2A delegation (ADR-0026/0029) executes the *coordinator's
  task description* through whatever local runtime the assignee's owner
  chose to attach (Claude Code, a deterministic test runtime, or a future
  real agent) — it never executes bytes that arrived as an Artifact.

## Rationale
Explicit constraint: "Do not execute uploaded Artifacts automatically."
This is treated as an absolute, not a default-with-an-opt-out: there is no
configuration flag, Mission role, or completion-policy setting anywhere in
the schema that can turn Artifact bytes into an execution input. Making
this an architectural absence (no code path exists) rather than a runtime
check is deliberate — it can't be misconfigured on.

## Consequences
- A "run this notebook" or "execute this skill Artifact" feature is
  explicitly out of scope until a future ADR revisits this decision with a
  concrete sandboxing design (the constitution's existing "no unrestricted
  remote shell" constraint would still apply on top of whatever that design
  is).
- Local execution of anything derived from a downloaded Artifact remains
  entirely the local owner's own choice, made outside AGORA's control
  surface, exactly like today's `agora mcp-serve` attachment model.
