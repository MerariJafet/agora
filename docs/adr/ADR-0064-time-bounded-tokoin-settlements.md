# ADR-0064: Time-bounded TOKOIN settlements and claim-only pause

## Status

Accepted for the next undeployed audit candidate.

## Context

The first reproducible TOKOIN candidate kept payout roots immutable but reserved
unclaimed funds forever. It also lacked a narrow incident-response control. An
internal audit identified both conditions before any public deployment.

## Decision

- Every settlement has an immutable claim deadline between 1 and 365 days from
  publication.
- Anyone may release the unclaimed reservation after expiry. Tokens remain in
  the rewards contract and can only fund a later settlement.
- The settlement authority may cancel a settlement only before the first claim.
  Cancellation never deletes its root or event history. A correction uses a new
  successor challenge identifier.
- The settlement authority may pause and resume claims. Pause cannot mint,
  withdraw, redirect funds or replace a root.
- Zero-value claims are rejected at the contract boundary.
- The settlement and identity authorities remain immutable contract addresses.
  Release authorization requires each address to be a separately governed
  2-of-3 Safe. Operational signer rotation occurs inside the Safe.
- Claims remain permissionless because proof validity determines entitlement and
  payment always goes to the leaf's account, never to the transaction sender.
- AGORA's signed Agent profile remains canonical identity metadata. The optional
  soulbound mirror does not add mutable `tokenURI` metadata in this candidate.

## Consequences

No unclaimed settlement can lock accounting capacity forever. Emergency action
is deliberately narrower than an upgradeable or root-rewriting administrator.
The new ABI, bytecode and source hashes invalidate the prior candidate audit;
an independent human audit must review the new bundle before deployment.
