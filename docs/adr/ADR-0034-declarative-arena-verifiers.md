# ADR-0034: Declarative Arena Verifiers First

Status: Accepted

Sprint 06 supports objective verification through declarative manifests:
`exact_text`, `numeric`, `simulated_outcome` and `manual`. The API core never
executes arbitrary submitted code or verifier code.

Coding/build challenges can be represented as Arena metadata, but executable
sandboxing belongs to later module/sandbox work. Until that isolation exists,
uploaded artifacts and submissions remain untrusted data.

This preserves the AGORA rule that remote content cannot obtain local or
server execution authority merely by being part of a Challenge.
