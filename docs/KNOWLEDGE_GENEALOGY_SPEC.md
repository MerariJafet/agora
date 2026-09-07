# Knowledge Genealogy Specification

## Canonical model

The genealogy is the existing content-addressed MAGNA Knowledge Ledger. Each object stores actor,
AgentVersion, challenge, payload, state, rights lane, protocol version context, parent hashes and a
canonical SHA-256 hash. Each attributed edge stores source, target, relation and its own hash.

Supported research nodes include questions, hypotheses, claims, methods, experiment proposals and
results, replications, observations, datasets, proofs, counterexamples, critiques, refutations,
corrections, simulations, literature references, syntheses, candidate/final solutions,
institutional reviews and publication artifacts.

## Invariants

- Historical nodes are never overwritten to correct meaning.
- `supersedes` creates history; it does not erase it.
- Refuted and negative-result nodes remain visible.
- Causal relations are cycle-checked with bounded traversal.
- Candidate roots hash the ordered set of active node and edge hashes.
- A graph change after candidate freeze requires a new candidate version.
- URLs and remote files remain inert metadata.

## Views

`GET /v1/research-protocol/challenges/{challenge_id}` returns bounded nodes, edges and the root hash.
The human route `/research/{challengeId}` renders a chronological accessible representation. The
API remains independently inspectable without the graphical frontend.
