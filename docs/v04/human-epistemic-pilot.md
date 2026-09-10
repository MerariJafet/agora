# V04-F — Human Epistemic Pilot

Until now, epistemic reviewers were software or experimental identities.
This pilot proves the pipeline with **real human reviewers**:

```
Human reviewer
  → AGORA identity (hum_ prefixed, own key)
  → commit
  → review
  → reveal
  → signed ReviewReceipt
  → scientific resolution
  → TOKOIN TEST reward
```

## The critical experimental property

A human reviewer must be able to say **REJECT — and get paid** for the
review work, provided the review meets protocol requirements.

This tests, with humans, the V0.3 review-economics change: the reward buys
**verifiable epistemic work**, never a favorable verdict. A pilot where
every reviewer approves proves nothing; the protocol requires at least one
scenario where the correct professional answer is REJECT or INCONCLUSIVE.

## Who (deliberately modest)

Not Harvard, not MIT, not an institutional agreement. Two real
researchers, preferably from different organizations, willing to perform
one documented experimental review each. Institutional pilots come after
the mechanism is proven. Reviewers are named in the published record only
with their consent; pseudonymous participation with a verified-key
identity is acceptable for the pilot.

## Protocol

1. Reviewer receives: scenario package (public), the V0.4 result schema,
   payment terms in TOKOIN TEST (explicitly non-monetary, non-transferable).
2. Reviewer creates their AGORA identity and key locally (assisted by
   docs only — their onboarding friction is a measured outcome, same rule
   as the operator rehearsal).
3. Commit → review → reveal within the protocol window.
4. `ScientificResultV04` submitted; ReviewReceipt signed.
5. Resolution runs; reward settles on the native network; reviewer
   confirms they can verify their own receipt and balance from the public
   state.

## Measured outcomes

```
onboarding_time + friction log
review_duration
verdict distribution (must include ≥1 paid REJECT/INCONCLUSIVE)
receipt verification by the reviewer themselves: yes/no
reviewer-reported trust/objections (free text, published verbatim)
```
