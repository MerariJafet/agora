import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { DEPLOY_ACK, evaluatePublicTestnetReadiness } from "../scripts/release-preflight-lib.mjs";
import { buildCandidateBundle } from "../scripts/candidate-bundle-lib.mjs";

function fixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "agora-tokoin-preflight-"));
  const auditPath = path.join(root, "audit.json");
  const independencePath = path.join(root, "independence.json");
  const authorizationPath = path.join(root, "authorization.json");
  const candidateBundlePath = path.join(root, "candidate.json");
  const contractRoot = path.resolve(import.meta.dirname, "..");
  const candidate = buildCandidateBundle(contractRoot);
  fs.writeFileSync(candidateBundlePath, JSON.stringify(candidate));
  fs.writeFileSync(auditPath, JSON.stringify({
    status: "COMPLETE_PASSED",
    report_hash: "a".repeat(64),
    contract_release_bundle_hash: candidate.bundle_sha256,
    accepted_by_operator: true,
    critical_findings: 0,
    high_findings: 0,
  }));
  fs.writeFileSync(independencePath, JSON.stringify({
    status: "INDEPENDENT_CONFIRMED",
    auditor: "Independent Security Reviewer",
    relationship_disclosure: "No financial or development relationship with the candidate.",
    accepted_by_operator: true,
  }));
  const env = {
    AGORA_TOKOIN_DEPLOY_ACK: DEPLOY_ACK,
    TOKOIN_GENESIS_TREASURY_ADDRESS: `0x${"12".repeat(20)}`,
    TOKOIN_SETTLEMENT_AUTHORITY_ADDRESS: `0x${"34".repeat(20)}`,
    AGORA_IDENTITY_ISSUER_ADDRESS: `0x${"56".repeat(20)}`,
    TOKOIN_TREASURY_CONTROL: "SAFE_2_OF_3",
    TOKOIN_SETTLEMENT_CONTROL: "SAFE_2_OF_3",
    AGORA_IDENTITY_ISSUER_CONTROL: "SAFE_2_OF_3",
    TOKOIN_RELEASE_COMMIT: "d".repeat(40),
    TOKOIN_MAX_TEST_ETH_BUDGET_WEI: "10000000000000000",
  };
  fs.writeFileSync(authorizationPath, JSON.stringify({
    network: "BASE_SEPOLIA",
    chain_id: 84532,
    authorize_transaction: true,
    scope: "TOKOIN_PUBLIC_TESTNET_NO_ECONOMIC_VALUE",
    external_audit_report_hash: "a".repeat(64),
    contract_release_bundle_hash: candidate.bundle_sha256,
    treasury_address: env.TOKOIN_GENESIS_TREASURY_ADDRESS,
    settlement_authority_address: env.TOKOIN_SETTLEMENT_AUTHORITY_ADDRESS,
    identity_issuer_address: env.AGORA_IDENTITY_ISSUER_ADDRESS,
    release_commit: env.TOKOIN_RELEASE_COMMIT,
    maximum_test_eth_budget_wei: env.TOKOIN_MAX_TEST_ETH_BUDGET_WEI,
    authorized_by: ["founder", "security-reviewer"],
    authorized_at: "2026-09-06T20:00:00Z",
  }));
  return { auditPath, independencePath, authorizationPath, candidateBundlePath, env };
}

test("complete audit, narrow authorization and multisig declaration pass", () => {
  assert.equal(evaluatePublicTestnetReadiness(fixture()).ready, true);
});

test("missing audit and authorization fail closed", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "agora-tokoin-missing-"));
  const result = evaluatePublicTestnetReadiness({
    auditPath: path.join(root, "missing-audit.json"),
    independencePath: path.join(root, "missing-independence.json"),
    authorizationPath: path.join(root, "missing-authorization.json"),
    candidateBundlePath: path.join(root, "missing-candidate.json"),
    env: {},
  });
  assert.equal(result.ready, false);
  assert.ok(result.blockers.includes("external_audit_not_complete"));
  assert.ok(result.blockers.includes("auditor_independence_not_confirmed"));
  assert.ok(result.blockers.includes("transaction_not_authorized"));
  assert.ok(result.blockers.includes("deploy_ack_missing"));
});

test("mainnet or a single-key treasury cannot pass", () => {
  const input = fixture();
  fs.writeFileSync(input.authorizationPath, JSON.stringify({
    network: "BASE_MAINNET",
    chain_id: 8453,
    authorize_transaction: true,
    scope: "TOKOIN_PUBLIC_TESTNET_NO_ECONOMIC_VALUE",
    external_audit_report_hash: "a".repeat(64),
    treasury_address: input.env.TOKOIN_GENESIS_TREASURY_ADDRESS,
    settlement_authority_address: input.env.TOKOIN_SETTLEMENT_AUTHORITY_ADDRESS,
    identity_issuer_address: input.env.AGORA_IDENTITY_ISSUER_ADDRESS,
  }));
  input.env.TOKOIN_TREASURY_CONTROL = "EOA";
  input.env.TOKOIN_SETTLEMENT_CONTROL = "EOA";
  input.env.AGORA_IDENTITY_ISSUER_CONTROL = "EOA";
  const result = evaluatePublicTestnetReadiness(input);
  assert.equal(result.ready, false);
  assert.ok(result.blockers.includes("network_not_authorized"));
  assert.ok(result.blockers.includes("chain_not_authorized"));
  assert.ok(result.blockers.includes("treasury_multisig_attestation_missing"));
  assert.ok(result.blockers.includes("settlement_multisig_attestation_missing"));
  assert.ok(result.blockers.includes("identity_issuer_multisig_attestation_missing"));
});

test("authorization cannot substitute audited control addresses", () => {
  const input = fixture();
  const authorization = JSON.parse(fs.readFileSync(input.authorizationPath, "utf8"));
  authorization.settlement_authority_address = `0x${"78".repeat(20)}`;
  fs.writeFileSync(input.authorizationPath, JSON.stringify(authorization));
  const result = evaluatePublicTestnetReadiness(input);
  assert.equal(result.ready, false);
  assert.ok(result.blockers.includes("authorized_settlement_authority_mismatch"));
});

test("audit and authorization must bind the exact candidate bundle", () => {
  const input = fixture();
  const audit = JSON.parse(fs.readFileSync(input.auditPath, "utf8"));
  audit.contract_release_bundle_hash = "f".repeat(64);
  fs.writeFileSync(input.auditPath, JSON.stringify(audit));
  const result = evaluatePublicTestnetReadiness(input);
  assert.equal(result.ready, false);
  assert.ok(result.blockers.includes("audit_candidate_bundle_hash_mismatch"));
});

test("control roles must use three distinct multisig addresses", () => {
  const input = fixture();
  const authorization = JSON.parse(fs.readFileSync(input.authorizationPath, "utf8"));
  input.env.AGORA_IDENTITY_ISSUER_ADDRESS = input.env.TOKOIN_SETTLEMENT_AUTHORITY_ADDRESS;
  authorization.identity_issuer_address = input.env.AGORA_IDENTITY_ISSUER_ADDRESS;
  fs.writeFileSync(input.authorizationPath, JSON.stringify(authorization));
  const result = evaluatePublicTestnetReadiness(input);
  assert.equal(result.ready, false);
  assert.ok(result.blockers.includes("control_role_concentration_rejected"));
});
