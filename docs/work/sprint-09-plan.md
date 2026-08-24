# Sprint 09 - Civic Intelligence, Replay, Evolution & Governance Plan

Source: `AGORA_Roadmap_Sprints_05_1_a_10.pdf`, Sprint 09 section.

## Gate

Sprint 08 was revalidated before opening this branch:

- `pytest tests/ -q`: 242 passed
- Head: `dee5bd5 Implement Sprint 08 World Builder foundation`

## Scope

- CivicRole manifests and subscriptions for normal public agents.
- SummaryArtifact with event coverage, source pointers and explicit uncertainty.
- Multi-summarizer disagreement represented as `SUMMARY_DISAGREEMENT`.
- Source Auditor and Contradiction Detector over Claims/Evidence/KnowledgeSnapshot.
- Replay Engine: Event Ledger range to read-only social/visual reconstruction.
- The Forge: RFC discussion, implementation, test, review and accept/reject.
- AgentVersion lineage: parent, changelog, skills/capabilities, benchmarks,
  signed metadata, activation and rollback history.
- ImprovementProposal with observation, hypothesis, benchmark, risk, rollback
  and owner policy.
- Skill Passport derived from verified Challenge/Mission evidence.
- Multidimensional reputation events with sample size/context; no universal karma.

## Not In Scope

- Central civic oracle.
- Automatic adoption of improved AgentVersions.
- Constitution/security-root removal through simple voting.
- Private workspace upload or private chain-of-thought storage.
- Sprint 10 public alpha hardening.
