import fs from "node:fs";

import { buildSettlementBundle } from "./settlement-bundle-lib.mjs";

const [inputPath, outputPath] = process.argv.slice(2);
if (!inputPath || !outputPath) {
  throw new Error("usage: npm run settlement:build -- INPUT.json OUTPUT.json");
}
const input = JSON.parse(fs.readFileSync(inputPath, "utf8"));
const bundle = buildSettlementBundle(input);
fs.writeFileSync(outputPath, `${JSON.stringify(bundle, null, 2)}\n`, { flag: "wx" });
console.log(JSON.stringify({ ok: true, output: outputPath, payout_root: bundle.payout_root }));
