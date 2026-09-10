import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import { spawnSync } from "node:child_process";
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

test("explicit bundle CLI validates current candidate and rejects tampering or missing files", () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "tokoin-candidate-cli-"));
  try {
    const bundlePath = path.join(temp, "candidate.json");
    const invoke = (file) => spawnSync(process.execPath, [
      path.join(root, "scripts/verify-candidate-bundle.mjs"), file,
    ], { cwd: temp, encoding: "utf8" });
    const candidate = buildCandidateBundle(root);
    fs.writeFileSync(bundlePath, JSON.stringify(candidate));
    assert.equal(invoke("candidate.json").status, 0);
    candidate.target.mainnet_authorized = true;
    fs.writeFileSync(bundlePath, JSON.stringify(candidate));
    assert.notEqual(invoke(bundlePath).status, 0);
    assert.notEqual(invoke("missing.json").status, 0);
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
});
