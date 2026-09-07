import fs from "node:fs";
import path from "node:path";

import { buildCandidateBundle } from "./candidate-bundle-lib.mjs";

const root = path.resolve(import.meta.dirname, "..");
const outputPath = path.resolve(
  root,
  "../../audit/tokoin-testnet/release-candidate/contract-release-bundle-v1.json",
);
const bundle = buildCandidateBundle(root);
fs.writeFileSync(outputPath, `${JSON.stringify(bundle, null, 2)}\n`);
console.log(JSON.stringify({ ok: true, output: outputPath, bundle_sha256: bundle.bundle_sha256 }));
