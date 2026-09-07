import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

import { buildCandidateBundle, validateCandidateBundle } from "./candidate-bundle-lib.mjs";

const root = path.resolve(import.meta.dirname, "..");
const bundlePath = path.resolve(
  root,
  "../../audit/tokoin-testnet/release-candidate/contract-release-bundle-v1.json",
);
const recorded = JSON.parse(fs.readFileSync(bundlePath, "utf8"));
const current = buildCandidateBundle(root);
assert.equal(validateCandidateBundle(recorded), true, "recorded bundle hash is invalid");
assert.deepEqual(recorded, current, "contract source/build artifacts differ from release bundle");
console.log(JSON.stringify({ ok: true, bundle_sha256: recorded.bundle_sha256 }));
