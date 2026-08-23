# ADR-0024: No Arbitrary Evidence URL Fetching (SSRF Prevention)

Status: Accepted · Date: 2026-08-23

## Decision
AGORA Cloud never performs a network request against a client-supplied
Evidence `locator`. There is no HTTP client, no redirect resolver and no
"preview fetcher" anywhere in `claims_service.py`, `graph_service.py` or the
claims/evidence routes — the field is validated as a string (length, basic
syntax where relevant) and stored verbatim.

This closes SSRF by construction rather than by an allow/deny list: there is
no code path that could reach `locator`'s value with a socket, so there is
nothing to bypass with `http://localhost/`, `http://127.0.0.1/`,
`http://[::1]/`, `http://169.254.169.254/` (cloud metadata service),
RFC1918 ranges (`10.x`, `172.16-31.x`, `192.168.x`), or `file://` schemes.

Verified with `tests/security/test_epistemic_security.py`:
`test_ssrf_locators_never_cause_network_access` wraps Evidence creation in a
`socket.socket.connect` guard that fails the test if ANY new connection is
attempted — the strongest available proof for a black-box test — for every
locator in the list above, plus one exercised through the atomic
claim+evidence creation path.

## Rationale
Explicit sprint constraint: "Do not fetch arbitrary user-provided URLs from
AGORA Cloud" and "Allow URLs to reach localhost, RFC1918, metadata services
or internal networks through any indirect feature" is forbidden. A
preview-fetch or link-unfurl feature is exactly the kind of "indirect
feature" that historically reintroduces SSRF in other systems — Sprint 04
does not build one.

## Consequences
- "Evidence preview" (fetching a page title/thumbnail server-side) is
  explicitly out of scope until a sprint designs it with an egress-controlled
  fetcher (allow-list, DNS-rebinding protection, private-IP blocking at the
  network layer) — this ADR is the reminder that a naive implementation
  would violate this decision.
- The browser MAY let a human click through to `locator` themselves
  (`rel="noopener noreferrer"`, opened by explicit user action) — that is the
  reader's own outbound request, not AGORA's.
