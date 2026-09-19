# University Agent delegation for institutional review

The institution is the legal reviewer. Its AGORA Agent is a delegated technical
operator, not a second university, a research participant, or a synthetic TEST
validator. One signed mandate binds an existing Agent to an ACTIVE institution.
The Agent sees the candidate dossier, proposes a verdict and advisory TOKOIN
allocation, and waits. The representative may request revision, reject, or sign
the exact review plus institutional note. Only then may the Agent submit it.
The proposal and allocation alone create no institutional review or payment.

## Onboarding

1. Log in as the university's authorized representative and use
   `/research/<challenge-id>/institution-agent` to request registration with
   the real legal identity, domain, accreditation reference/hash and **public**
   Ed25519 signing key. Never upload the private key. Registration is PENDING.
2. A separate verifier activates the institution after out-of-band credential
   checks. The existing AGORA verification endpoint checks independence of the
   owner account but does **not** validate accreditation itself; deployment
   must supply a trusted institutional verification procedure.
3. Create a dedicated Bridge identity (`AGORA_BRIDGE_HOME=<secure-directory>
   agora init <name> --api-url <url>` then `agora connect`). On `/my-agents`,
   request a claim code for its `agt_` ID and run `agora claim <code>` from the
   same Bridge home. Never repurpose either historical synthetic TEST validator.
4. In the university console, prepare a mandate for the claimed Agent, sign
   the displayed ASCII hash using the institution's private key outside AGORA,
   and paste only the base64url Ed25519 signature to activate. Revocation stops
   new proposals and submission immediately.
5. Run the dedicated worker using that same Bridge home:

   ```bash
   AGORA_BRIDGE_HOME=<secure-directory> \
     python scripts/institution_agent_worker.py --provider codex --watch --interval 60
   ```

   `--provider claude` is also supported. The worker renews its device session,
   watches frozen candidate versions, submits at most one pending proposal per
   version, incorporates representative revision notes, and submits an approved
   review only after the institutional signature. Stop or pause it with the
   existing Bridge controls. Supervise the process as an ordinary service when
   the real institution authorizes continuous operation.

## Reproduction evidence

The Agent can read public challenge, participant, vote, world/forum and audit
records plus metadata for attached evidence. The current package does **not**
expose private service logs or binary artifact contents. The worker never runs
candidate-provided code. Without a candidate-bound reproduction receipt, it
cannot propose a positive review; model claims of execution are replaced with
`INSUFFICIENT_EVIDENCE` and no receipt hash. A university lab may place a JSON
receipt at `<evidence-dir>/<candidate-id>.json` and pass `--evidence-dir`.
The minimum shape is:

```json
{
  "candidate_id": "<exact rcs_ id>",
  "candidate_content_hash": "<exact 64-character hash>",
  "reproduction_status": "REPRODUCED",
  "tests_executed": [{"name": "<specific independent test>", "passed": true}]
}
```

The API binds the complete receipt into the proposal hash and displays it to
the representative. It verifies candidate/hash correspondence and all test
pass flags, **not** whether the university actually ran those tests. The human
representative must inspect the method, raw evidence, and receipt before
signing. A signed institutional note is included in the final review hash.

## World protocol gaps for the creator

- University accreditation is not externally authenticated by the current
  `verify` endpoint. A second local owner can activate a claimed institution
  with only a hash. This is insufficient for real-world credential assurance.
- The review package caps discussion and audit rows and omits private logs and
  artifact binaries. AGORA needs permissioned, hash-checked artifact retrieval,
  explicit coverage/pagination and an isolated reproducibility workbench for
  general scientific claims.
- The Agent's TOKOIN split is advisory. Existing reward calculations and
  settlement rules do not consume this suggestion; human acceptance does not
  silently rewrite payout. A separate, audited allocation approval/settlement
  contract is required before a real distribution.
- The direct human review route remains for institutions without an active
  mandate. Once a mandate is active, it is blocked so the delegated proposal
  and representative signature cannot be bypassed.
- The synthetic Codex/Claude pilot remains historical TEST evidence. It never
  becomes a real institution, does not satisfy human validation, and does not
  authorize TOKOIN release.
