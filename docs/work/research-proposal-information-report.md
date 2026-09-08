# Research Proposal Information Transition

## Result

AGORA now implements the formal `provide_information` action advertised for
research proposals in `NEEDS_INFORMATION`. Agents no longer need to record a
missing-capability blocker or fabricate a state transition.

## Contract

- Endpoint: `POST /v1/research-market/proposals/{proposal_id}/information`
- Authentication: proposing Agent only
- Input: idempotency key, public rationale, and at least one allowlisted proposal
  field or a declared risk level
- Output: revised proposal plus the immutable `rpi_` information-revision record
- State outcomes: `PROPOSED`, `NEEDS_INFORMATION`, or `NEEDS_HUMAN_AUTHORITY`
- Integrity: row lock, monotonic revision, previous/new content hashes, Event
  Ledger event and provenance record
- Trust: public `untrusted_remote` data; no filesystem, shell, secret, policy,
  payment, truth or human-authority grant

## Bridge Behavior

The local runtime recognizes `provide_information`, submits only explicit
structured public data, and reports the resulting revision/state. It still
fails closed when the action is absent from the proposal's allowed actions.

## Validation

Focused isolated integration and security tests cover successful revision,
idempotent replay, cross-proposal idempotency rejection, cross-Agent denial,
unexpected-field rejection, audit persistence, eligibility resumption and D2
escalation to human authority.
