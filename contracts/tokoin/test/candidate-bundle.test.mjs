import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";

import {
  buildCandidateBundle,
  canonicalJson,
  validateCandidateBundle,
} from "../scripts/candidate-bundle-lib.mjs";

const root = path.resolve(import.meta.dirname, "..");

test("candidate bundle binds source, build inputs, ABI and bytecode", () => {
  const bundle = buildCandidateBundle(root);
  assert.equal(validateCandidateBundle(bundle), true);
  assert.deepEqual(Object.keys(bundle.contracts).sort(), [
    "AgoraAgentIdentity",
    "TokoinFixedSupply",
    "TokoinResearchRewards",
  ]);
  assert.equal(bundle.target.chain_id, 84532);
  assert.equal(bundle.monetary_policy.total_supply_aceros, "100000000000000");
});

test("candidate bundle detects metadata tampering", () => {
  const bundle = buildCandidateBundle(root);
  const tampered = structuredClone(bundle);
  tampered.target.mainnet_authorized = true;
  assert.equal(validateCandidateBundle(tampered), false);
});

test("canonical JSON is independent of object insertion order", () => {
  assert.equal(canonicalJson({ b: 2, a: 1 }), canonicalJson({ a: 1, b: 2 }));
});
