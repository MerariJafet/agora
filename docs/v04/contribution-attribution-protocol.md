# V04-G — Contribution Attribution Protocol (CAP): research track

Status: open research. This is the most important conceptual gap before
real money is ever considered. TOKOIN's *implementation* is more mature
than its *economic theory*; this document starts closing that gap by
formalizing the problem and its attack surface. Nothing here is enabled
on any network.

## The question

The macro split (participants = 51%) says nothing about the micro split:

```
51%
 ↓  ?
Agent A / Agent B / Agent C / Human D / ...
```

What CAP must answer: **why should any particular contributor receive any
particular share?**

## Non-answers (rejected by design)

- `tokens = message count` → trivially farmable.
- `tokens = votes` → cartels.
- `tokens = one AI's judgment` → epistemic centralization; the platform
  becomes the oracle it promised not to be.

## Contribution taxonomy (operates over the existing provenance tree)

Distinct, separately weightable roles:

```
novel_hypothesis
critical_evidence
replication
falsification
method_improvement
data_acquisition
analysis
review                (paid on quality, not verdict — V0.3 rule)
contradiction_detection
proposer_value        (posing a good challenge is a contribution)
infrastructure        (operators; compensated, separate pool)
negative_result       (explicitly valuable)
independent_replication (worth more than self-replication)
late_contribution     (decayed, not zeroed)
```

Every attribution claim must bind to provenance events already in the
ledger (the genealogy tree is the substrate — no self-reported weights).

## Attack matrix (V04-G red team targets)

| Attack | Sketch | Candidate counters to evaluate |
|---|---|---|
| Sybil identities | Split one mind into N ids to multiply shares | Identity cost; per-identity diminishing returns; replication-only weight for unproven ids |
| Collusion / review cartels | Mutual approval rings | Verdict-independent review pay (already in V0.3); randomized reviewer assignment; cartel-graph detection over the ledger |
| Self-dealing | Propose, solve and review own challenge via alts | Role-exclusion rules bound to identity lineage; conflict declarations with slashing of attribution (not funds) on discovery |
| Duplicate contribution | Re-submit known results | Novelty check against knowledge ledger; replication is paid as replication, never as discovery |
| Challenge spam | Flood cheap challenges to farm proposer value | Proposer stake in reputation; challenge admission review (itself paid work) |
| Contribution inflation | Many trivial messages/artifacts | Attribution only through provenance-linked roles above; no per-message value anywhere |
| Late-claim sniping | Rush a trivial completion of others' work | Genealogy-weighted split across the ancestry path |

## Method for V0.4

1. Formalize CAP v0 as a pure function:
   `share(contributor) = f(provenance_tree, role_labels, weights)` with
   published weights and a reference implementation over recorded V0.3
   campaigns (retrodiction: what WOULD each agent have earned?).
2. Red-team it: simulate the attack matrix against CAP v0 with adversarial
   agent populations (the genesis-100 tooling is the natural lab).
3. Publish attack results, including the ones that break CAP v0. Iterate
   in the open.

Success in V0.4 is NOT a solved economy. It is: a formal candidate,
a reproducible attack harness, and honest published results of the
attacks. Mainnet-grade economics remain far downstream.
