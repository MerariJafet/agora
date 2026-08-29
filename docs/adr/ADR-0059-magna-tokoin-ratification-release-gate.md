# ADR-0059: MAGNA TOKOIN Ratification Release Gate

Status: Accepted

## Context

Sprint 04 introduced an audit-ready local-devnet TOKOIN plane, but human
ratifications and independent audit evidence are intentionally outside what the
software agent may fabricate.

## Decision

AGORA exposes scope, ratification and release-manifest artifacts as read-only
release-gate data. Pending ratifications remain unsigned and have
`decision_value=null`. Only `TokoinFixedSupply` is represented as implemented
contract source; off-chain controls remain explicit trust boundaries.

Sprint 05 must not begin from this state unless the human owner changes the
roadmap gate or supplies accepted independent audit evidence and final go/no-go.

## Consequences

- Local technical work is preserved in Git.
- Public-testnet and mainnet claims remain blocked.
- Future reviewers can audit exactly which components are contracts, off-chain
  controls or deferred scope.
