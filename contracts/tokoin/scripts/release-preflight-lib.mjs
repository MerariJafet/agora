import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

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
  authorizationPath = path.join(
    repoRoot,
    "audit/tokoin-testnet/release-candidate/base-sepolia-deploy-authorization.json",
  ),
} = {}) {
  const audit = readJson(auditPath);
  const authorization = readJson(authorizationPath);
  const blockers = [];

  if (audit.status !== "COMPLETE_PASSED") blockers.push("external_audit_not_complete");
  if (audit.accepted_by_operator !== true) blockers.push("external_audit_not_accepted");
  if (!/^[0-9a-f]{64}$/i.test(String(audit.report_hash ?? ""))) {
    blockers.push("external_audit_hash_missing");
  }
  if (Number(audit.critical_findings ?? -1) !== 0) blockers.push("critical_findings_not_zero");
  if (Number(audit.high_findings ?? -1) !== 0) blockers.push("high_findings_not_zero");

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

  return {
    ready: blockers.length === 0,
    target: { network: "BASE_SEPOLIA", chain_id: BASE_SEPOLIA_CHAIN_ID },
    economic_value: false,
    mainnet_authorized: false,
    blockers,
  };
}
