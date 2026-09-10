import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { buildCandidateBundle, validateCandidateBundle } from "./candidate-bundle-lib.mjs";

export const BASE_SEPOLIA_CHAIN_ID = 84532;
export const DEPLOY_ACK = "DEPLOY TOKOIN TO BASE SEPOLIA TESTNET WITHOUT ECONOMIC VALUE";

const here = path.dirname(fileURLToPath(import.meta.url));
export const repoRoot = path.resolve(here, "../../..");

function readJson(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch (error) {
    return { _read_error: String(error) };
  }
}

export function evaluatePublicTestnetReadiness({
  env = process.env,
  auditPath = path.join(repoRoot, "audit/tokoin-testnet/external/audit-report-reference.json"),
  independencePath = path.join(
    repoRoot,
    "audit/tokoin-testnet/external/auditor-independence-disclosure.json",
  ),
  authorizationPath = path.join(
    repoRoot,
    "audit/tokoin-testnet/release-candidate/base-sepolia-deploy-authorization.json",
  ),
  candidateBundlePath = path.join(
    repoRoot,
    "audit/tokoin-testnet/release-candidate/contract-release-bundle-v1.json",
  ),
} = {}) {
  const audit = readJson(auditPath);
  const independence = readJson(independencePath);
  const authorization = readJson(authorizationPath);
  const candidateBundle = readJson(candidateBundlePath);
  const blockers = [];

  if (!validateCandidateBundle(candidateBundle)) blockers.push("candidate_bundle_invalid");
  {
    try {
      const current = buildCandidateBundle(path.join(repoRoot, "contracts/tokoin"));
      if (current.bundle_sha256 !== candidateBundle.bundle_sha256) {
        blockers.push("candidate_bundle_source_mismatch");
      }
    } catch {
      blockers.push("candidate_build_unavailable");
    }
  }
  if (audit.contract_release_bundle_hash !== candidateBundle.bundle_sha256) {
    blockers.push("audit_candidate_bundle_hash_mismatch");
  }

  if (audit.status !== "COMPLETE_PASSED") blockers.push("external_audit_not_complete");
  if (audit.accepted_by_operator !== true) blockers.push("external_audit_not_accepted");
  if (!/^[0-9a-f]{64}$/i.test(String(audit.report_hash ?? ""))) {
    blockers.push("external_audit_hash_missing");
  }
  if (Number(audit.critical_findings ?? -1) !== 0) blockers.push("critical_findings_not_zero");
  if (Number(audit.high_findings ?? -1) !== 0) blockers.push("high_findings_not_zero");
  if (
    independence.status !== "INDEPENDENT_CONFIRMED"
    || independence.accepted_by_operator !== true
    || typeof independence.auditor !== "string"
    || !independence.auditor.trim()
    || typeof independence.relationship_disclosure !== "string"
    || !independence.relationship_disclosure.trim()
  ) {
    blockers.push("auditor_independence_not_confirmed");
  }

  if (authorization.network !== "BASE_SEPOLIA") blockers.push("network_not_authorized");
  if (Number(authorization.chain_id) !== BASE_SEPOLIA_CHAIN_ID) {
    blockers.push("chain_not_authorized");
  }
  if (authorization.authorize_transaction !== true) blockers.push("transaction_not_authorized");
  if (authorization.scope !== "TOKOIN_PUBLIC_TESTNET_NO_ECONOMIC_VALUE") {
    blockers.push("authorization_scope_invalid");
  }
  if (authorization.external_audit_report_hash !== audit.report_hash) {
    blockers.push("authorization_audit_hash_mismatch");
  }
  if (authorization.contract_release_bundle_hash !== candidateBundle.bundle_sha256) {
    blockers.push("authorization_candidate_bundle_hash_mismatch");
  }
  if (!/^[0-9a-f]{40}$/i.test(String(env.TOKOIN_RELEASE_COMMIT ?? ""))) {
    blockers.push("release_commit_missing_or_invalid");
  }
  if (authorization.release_commit !== env.TOKOIN_RELEASE_COMMIT) {
    blockers.push("authorized_release_commit_mismatch");
  }
  if (!/^[1-9][0-9]*$/.test(String(env.TOKOIN_MAX_TEST_ETH_BUDGET_WEI ?? ""))) {
    blockers.push("test_eth_budget_missing_or_invalid");
  }
  if (authorization.maximum_test_eth_budget_wei !== env.TOKOIN_MAX_TEST_ETH_BUDGET_WEI) {
    blockers.push("authorized_test_eth_budget_mismatch");
  }
  if (
    !Array.isArray(authorization.authorized_by)
    || new Set(authorization.authorized_by).size < 2
    || authorization.authorized_by.some((item) => typeof item !== "string" || !item.trim())
  ) {
    blockers.push("independent_authorizers_missing");
  }
  if (Number.isNaN(Date.parse(String(authorization.authorized_at ?? "")))) {
    blockers.push("authorization_timestamp_invalid");
  }
  if (env.AGORA_TOKOIN_DEPLOY_ACK !== DEPLOY_ACK) blockers.push("deploy_ack_missing");
  if (!/^0x[0-9a-fA-F]{40}$/.test(String(env.TOKOIN_GENESIS_TREASURY_ADDRESS ?? ""))) {
    blockers.push("treasury_address_missing_or_invalid");
  }
  if (!/^0x[0-9a-fA-F]{40}$/.test(String(env.TOKOIN_SETTLEMENT_AUTHORITY_ADDRESS ?? ""))) {
    blockers.push("settlement_authority_missing_or_invalid");
  }
  if (!/^0x[0-9a-fA-F]{40}$/.test(String(env.AGORA_IDENTITY_ISSUER_ADDRESS ?? ""))) {
    blockers.push("identity_issuer_missing_or_invalid");
  }
  if (env.TOKOIN_TREASURY_CONTROL !== "SAFE_2_OF_3") {
    blockers.push("treasury_multisig_attestation_missing");
  }
  if (env.TOKOIN_SETTLEMENT_CONTROL !== "SAFE_2_OF_3") {
    blockers.push("settlement_multisig_attestation_missing");
  }
  if (env.AGORA_IDENTITY_ISSUER_CONTROL !== "SAFE_2_OF_3") {
    blockers.push("identity_issuer_multisig_attestation_missing");
  }
  if (authorization.treasury_address !== env.TOKOIN_GENESIS_TREASURY_ADDRESS) {
    blockers.push("authorized_treasury_mismatch");
  }
  if (authorization.settlement_authority_address !== env.TOKOIN_SETTLEMENT_AUTHORITY_ADDRESS) {
    blockers.push("authorized_settlement_authority_mismatch");
  }
  if (authorization.identity_issuer_address !== env.AGORA_IDENTITY_ISSUER_ADDRESS) {
    blockers.push("authorized_identity_issuer_mismatch");
  }
  const controlAddresses = [
    env.TOKOIN_GENESIS_TREASURY_ADDRESS,
    env.TOKOIN_SETTLEMENT_AUTHORITY_ADDRESS,
    env.AGORA_IDENTITY_ISSUER_ADDRESS,
  ].map((value) => String(value ?? "").toLowerCase());
  if (new Set(controlAddresses).size !== 3) blockers.push("control_role_concentration_rejected");

  return {
    ready: blockers.length === 0,
    target: { network: "BASE_SEPOLIA", chain_id: BASE_SEPOLIA_CHAIN_ID },
    economic_value: false,
    mainnet_authorized: false,
    blockers,
  };
}
