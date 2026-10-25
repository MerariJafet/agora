// npm audit --audit-level=high, minus advisories explicitly accepted in
// audit-allowlist.json until their expiry date. Anything else high/critical
// (or an expired exception) fails, exactly like the plain npm audit did.
import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";

const FAIL_LEVELS = new Set(["high", "critical"]);
const allowlist = JSON.parse(readFileSync(new URL("../audit-allowlist.json", import.meta.url)));
const today = new Date().toISOString().slice(0, 10);
const accepted = new Map(allowlist.advisories.map((a) => [a.id, a]));

let raw;
try {
  // Fixed command string (no interpolation); works with npm.cmd on Windows too.
  raw = execSync("npm audit --json", { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
} catch (error) {
  raw = error.stdout; // npm audit exits non-zero when it finds anything
}
const report = JSON.parse(raw);

const blocking = [];
const waived = [];
for (const [name, vuln] of Object.entries(report.vulnerabilities ?? {})) {
  if (!FAIL_LEVELS.has(vuln.severity)) continue;
  // Root advisories carry objects in `via`; transitive entries only name packages.
  const ids = vuln.via
    .filter((v) => typeof v === "object" && FAIL_LEVELS.has(v.severity))
    .map((v) => v.url.split("/").pop());
  const viaPackages = vuln.via.filter((v) => typeof v === "string");
  const unaccepted = ids.filter((id) => !(accepted.has(id) && accepted.get(id).expires >= today));
  const expired = ids.filter((id) => accepted.has(id) && accepted.get(id).expires < today);
  if (unaccepted.length || (ids.length === 0 && viaPackages.some((p) => !isWaivedOnly(p)))) {
    blocking.push(`${name} (${vuln.severity}) ${unaccepted.join(", ") || "via " + viaPackages.join(", ")}`);
  } else {
    waived.push(`${name} (${vuln.severity}) ${ids.join(", ") || "via " + viaPackages.join(", ")}`);
  }
  for (const id of expired) blocking.push(`${id}: allowlist entry expired ${accepted.get(id).expires}`);
}

function isWaivedOnly(pkg, seen = new Set()) {
  const vuln = report.vulnerabilities?.[pkg];
  if (!vuln || seen.has(pkg)) return true;
  seen.add(pkg);
  return vuln.via.every((v) =>
    typeof v === "string"
      ? isWaivedOnly(v, seen)
      : !FAIL_LEVELS.has(v.severity) ||
        (accepted.has(v.url.split("/").pop()) && accepted.get(v.url.split("/").pop()).expires >= today),
  );
}

for (const line of waived) console.log(`waived  ${line}`);
for (const line of blocking) console.log(`BLOCKED ${line}`);
if (blocking.length) process.exit(1);
console.log(`audit gate: no unaccepted high/critical advisories (${waived.length} waived)`);
