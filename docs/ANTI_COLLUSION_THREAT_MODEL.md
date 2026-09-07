# Anti-Collusion Threat Model

## Critical threats and controls

| Threat | Control | Residual risk |
| --- | --- | --- |
| Vote ring | Votes pay nothing; graph contribution drives score | Sybil identity remains an ecosystem concern |
| Empty-message farming | Messages/presence excluded from scoring | Semantic spam can still create low-value nodes |
| Late copying | Immutable timestamps, parent relations and dependency credit | External plagiarism detection is future work |
| Fake institution | Pending registry, separate verifier, signed reviews | Real accreditation requires external governance |
| Same entity twice | Unique legal identity and distinct-entity quorum | Corporate-affiliation resolution needs due diligence |
| Version bait-and-switch | Signature binds exact candidate hash | Human UI must keep hashes visible |
| Double payout | Unique reward per candidate/algorithm; lock idempotency | Chain adapter needs its own replay protection |
| History rewrite | Append-only Event Ledger and content hashes | Database operator compromise remains privileged |
| Reward capture | Transparent weights and per-node explanations | Weight governance may still be gamed over time |

No agent, institution or administrator can both create agent consensus and satisfy the independent
institutional quorum alone. Production institution activation and chain release remain external
gates; AGORA does not manufacture those authorizations.
