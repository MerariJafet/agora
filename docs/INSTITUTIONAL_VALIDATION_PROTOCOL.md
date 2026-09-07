# Institutional Validation Protocol

## Identity and onboarding

An institution records legal entity ID, name, domain, jurisdiction, Human Owner representative,
credential reference/hash, Ed25519 public key, conflicts and optional payout address. Registration
starts `PENDING`; the representative cannot activate its own institution. Production activation is
fail-closed pending a real accreditation operator and governance process.

## Review

The institution signs a canonical digest containing candidate ID/hash, institution ID, verdict,
methodology, evidence, paper and experiment reviews, and conflict declaration. One institution may
review an exact candidate only once. A materially changed candidate receives a new version and new
reviews.

Verdicts are `APPROVED`, `APPROVED_WITH_MINOR_CHANGES`, `REQUIRES_REVISION`, `REJECTED` and
`INSUFFICIENT_EVIDENCE`. Two approvals must come from distinct legal entity IDs. Any adverse verdict
on the current candidate blocks reward locking and sends the work back for revision.

Institutions are rewarded for completed review work, not for saying yes. Useful adverse reviews
from prior candidate versions remain in the final institutional work allocation. An adverse review
blocks its version, but does not erase the work that prevented an incorrect result from advancing.

The human portal prepares the exact canonical digest and accepts an externally produced Ed25519
signature. AGORA does not generate, import or retain an institution's private signing key.
