# ADR-0066: Agentic Research with Human Institutional Validation

## Status

Accepted for local protocol implementation. Public settlement remains gated.

## Context

AGORA already preserves immutable claims, evidence, artifacts, formal challenge actions and a
content-addressed knowledge ledger. Agent consensus could nominate an answer, but it could not
establish scientific truth or provide accountable human validation.

## Decision

AGORA separates six concerns: agentic research, knowledge genealogy, agent consensus, institutional
validation, reward settlement and publication. Agent consensus freezes a versioned candidate. At
least two active institutions with distinct legal identities must independently sign reviews of the
same candidate hash before a deterministic reward may be locked. The 1/10/60/20/9 allocation is
versioned and rewards contribution evidence, not message or vote volume.

The Event Ledger remains the immutable action history. The MAGNA Knowledge Ledger is extended as
the semantic genealogy rather than replaced. Publication packages bind the candidate, genealogy,
reviews, allocation and manuscript version. Human validation does not silently execute a public
TOKOIN transfer; deployment and settlement require their own audited control-plane release.

## Consequences

- Consensus remains useful without being mislabeled as truth.
- Corrections and adverse reviews require a new candidate version; old versions remain inspectable.
- Institutions are paid for review work, not for approving.
- The local protocol can prove reward eligibility while public settlement remains fail-closed.
- Institution onboarding and external scientific responsibility cannot be simulated by agents.
