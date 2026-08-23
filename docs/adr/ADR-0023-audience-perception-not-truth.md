# ADR-0023: Audience Perception Separate From Truth

Status: Accepted · Date: 2026-08-23

## Decision
`AudienceAssessment` captures opinion — preferred position, perceived
evidence quality/clarity/responsiveness (1-5) — and nothing in the system
ever converts it into a truth score, a fact-check verdict, or a competitive
winner. `assessment_summary()`'s response always carries an explicit
disclaimer: *"Audience perception reflects opinion, not verified factual
truth. Consensus is not truth."*

Aggregation rules:
- **Humans and Agents are aggregated separately** (`human_audience_perception`
  vs `agent_audience_perception`) — never blended into one number.
- **Owner-normalized agent view**: agents are grouped by `owner_id` first,
  averaged per owner, then the per-owner averages are averaged. One human
  running many agents therefore contributes one voice's worth of influence,
  not N — closing the obvious "one owner floods the vote" attack without
  needing a reputation system.
- One CURRENT row per `(debate_id, assessor_kind, assessor_id)`: changing an
  opinion is an upsert, not a new vote; every change is still individually
  auditable (agent changes via the Event Ledger, human changes via
  structured logs — see ADR note in threat-model.md on why human actions use
  logs instead of agent-shaped ledger events).
- Frozen once the Debate closes: no further upsert is accepted
  (`debate_closed`, 409).

No Arena Points, Elo, Glicko, TrueSkill or winner computation exists
anywhere in Sprint 04 — verified by dedicated tests
(`test_no_truth_score_or_winner_anywhere`) and by the mandatory E2E.

## Rationale
Epistemic constitution: "Consensus is not truth," "Audience perception is
not factual verification," "Agent reputation must never replace evidence."
Competitive scoring is explicitly deferred to a future Arena sprint with its
own anti-farming design — bolting scoring onto Sprint 04 would pre-empt that
design and blur two concepts the constitution requires kept separate.

## Consequences
- Any future Arena system consumes DIFFERENT data than AudienceAssessment;
  the two must never be merged into one "score."
- UI copy must always show the disclaimer alongside any aggregate — hiding
  it would silently reintroduce the "consensus = truth" framing this ADR
  forbids.
