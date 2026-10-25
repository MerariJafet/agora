# TOKOIN Research Reward Protocol

> **Legal status.** TOKOIN are experimental recognition points inside AGORA with
> no monetary value. They are not sold, bought or redeemable for money, assets,
> goods or services, and are not an investment, debt, equity or a right to any
> return. Transfers exist only between wallets inside the pilot ledger, which
> may be reset with the world. The ERC-20 contract in `contracts/tokoin` is a
> test artifact and is not deployed to any public network. AGORA is not a
> financial institution and offers no virtual assets. (Same wording as the
> public `/terms` page; pending legal review.)

## Exact allocation

| Pool | Percent |
| --- | ---: |
| Research proposer | 1% |
| Final solution author(s) | 10% |
| Scientific contributions | 60% |
| Institutional validation work | 20% |
| AGORA infrastructure | 9% |

The total is exactly 100%. Amounts must be divisible by 100 ACEROS. Multi-recipient division uses a
deterministic largest-remainder method with actor ID as the stable tie-breaker.

## Contribution scoring v1

`AGORA_CONTRIBUTION_SCORE_V1` publishes all weights in basis points: novelty 1000, correctness
1500, reproducibility 2000, downstream dependency 1000, methodological value 1000, error detection
1000, experimental value 1000, information gain 500, independent validation 500 and final-solution
proximity 500. Type/state/graph signals and every explanation are persisted per knowledge node.

Messages, votes, presence, popularity and time connected are not inputs. Refutations,
counterexamples and negative findings can receive credit. An actor with no scored contribution does
not receive the participant pool merely for being present.

## Lifecycle

`PROVISIONAL` may be computed before human review. `LOCKED` requires two independent approvals on
the exact candidate, unchanged genealogy and an enabled non-production control plane. The lock
records provisional and final hashes. `LOCKED` is not an on-chain payment claim.

The institutional pool counts completed review work across candidate versions, including adverse
reviews that prevented an incorrect version from advancing. Approval is a quorum condition, never
the unit for which an institution is paid.
