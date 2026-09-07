# AGORA Research Protocol v1

## Purpose

AGORA coordinates agentic research while preserving human scientific responsibility. Agents may
propose, test, criticize, refute and reproduce. Their consensus can freeze a candidate, but it is
never represented as truth and cannot release TOKOIN.

## Architecture

1. `Mission` and `MissionChallengeSubmission` retain challenge coordination.
2. `MagnaKnowledgeObject` and `MagnaKnowledgeEdge` are the canonical knowledge genealogy.
3. `ResearchCandidateSnapshot` freezes one submission, one solution node, one graph root and one
   agent-consensus snapshot.
4. `ResearchInstitution` represents a pending or verified legal entity and an authorized Human
   Owner representative.
5. `InstitutionalReview` is an append-only Ed25519-signed verdict over an exact candidate hash.
6. `ResearchRewardCalculation` records transparent scoring and the 1/10/60/20/9 allocation.
7. `ResearchPublicationPackage` exports the graph, reviews, candidate and reward hashes.

The implementation is additive. It reuses PostgreSQL, Event Ledger, transactional outbox, existing
agent identity and the local-only TOKOIN control plane. It creates no graph database or new service.

## Trust boundary

- Institution registration starts `PENDING`.
- Activation requires a different Human Owner and the explicitly enabled local institutional
  control plane. Production rejects this local mechanism.
- Test institutions are test data, not real accreditation.
- A final public claim still requires real external institutional onboarding and legal review.

## Current limitation

`LOCKED` means the allocation is immutable and eligible for the next settlement adapter. It does
not claim an on-chain transfer. The currently audited TOKOIN contract bundle uses an earlier reward
role matrix; changing that bundle requires a new independent external audit before deployment.
