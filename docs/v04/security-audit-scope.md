# V04-E — External Security Review: Scope

Why external: the agent that builds and the agent that evaluates share too
many presuppositions. The next serious review must be independent of both
the creator and the in-house autonomous tooling.

**Finding vulnerabilities is good news at this stage.** The engagement is
scoped so a reviewer does not need to audit CometBFT itself.

## In scope

```
TOKOIN application state machine
transaction signing / domain separation
nonce / replay rules
ProtocolTime integration
wallet / key handling
scientific commitment → reward binding
review commit/reveal
revocation
genesis assumptions
validator configuration
network exposure
upgrade / version handling
```

## Out of scope

CometBFT consensus internals, the web UI's cosmetic layer, and anything
already marked NO-GO and disabled (public economics, transfers, bridges).

## Deliverable

Findings classified `Critical / High / Medium / Low / Informational`, each
with reproduction steps. Response policy:

- Critical/High → fix + regression test + re-review before any Closed
  Testnet GO.
- Medium/Low → tracked publicly, scheduled.
- All findings and their resolutions are published with the V0.4 evidence
  pack (coordinated disclosure timing at the auditor's discretion).

## Materials provided to the auditor

Frozen V0.3 bundle + hash, protocol schemas, threat model, ADR index,
this scope, and the standing invariant list (SEC-001..008). No live access
to production-like infrastructure is required; everything runs locally.
