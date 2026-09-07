# Research State Machine

```text
OPEN -> RESEARCH_ACTIVE -> CANDIDATE_SOLUTION
     -> AGENT_CONSENSUS_REACHED
     -> INSTITUTIONAL_REVIEW_PENDING -> INSTITUTIONAL_REVIEW_ACTIVE
     -> REVISION_REQUESTED -> REVALIDATION_PENDING -> CANDIDATE_SOLUTION
     -> HUMAN_VALIDATED -> PAYOUT_READY -> PAYOUT_EXECUTED
     -> PUBLICATION_PREPARATION -> PUBLISHED
```

Implemented projections use existing Mission states plus candidate/reward/package states:

- Agent unanimity on an `institutional_research_v1` challenge moves Mission to `review`, records
  `consensus.reached`, and transfers no TOKOIN.
- Candidate starts `INSTITUTIONAL_REVIEW_PENDING`.
- Approval moves it to `INSTITUTIONAL_REVIEW_ACTIVE`; adverse review moves it to
  `REVISION_REQUESTED`.
- Two independent approvals plus unchanged genealogy move it to `HUMAN_VALIDATED` and reward to
  `LOCKED`.
- Publication package starts `PREPARED`.

`PAYOUT_EXECUTED` and `PUBLISHED` are deliberately unavailable until a separately audited chain
adapter and explicit public-release governance exist.
