# ADR-0035: Controlled Knowledge Adapter Registry

## Status

Accepted.

## Context

Sprint 07 connects AGORA to public knowledge without becoming a crawler or SSRF
primitive. Agents need current public-source metadata, but arbitrary user URLs
must remain inert.

## Decision

AGORA uses a declarative `KnowledgeSource` registry. Each source declares an
adapter id, allowed hosts, capabilities, freshness contract, license terms and
TTL. API clients select a registered source and query text; they cannot submit
an arbitrary URL for AGORA Cloud to fetch.

Sprint 07 adapters are deterministic local implementations with official source
metadata. Future live HTTP adapters must remain behind this boundary and obey
the same allowlist, redirect, timeout, size and content-type policies.

## Consequences

- Knowledge search is testable without credentials or network availability.
- SSRF risk is structurally reduced because Evidence locators remain inert and
  Knowledge routes do not dereference client-supplied URLs.
- Adding a new source requires registry/policy review, not just user input.
