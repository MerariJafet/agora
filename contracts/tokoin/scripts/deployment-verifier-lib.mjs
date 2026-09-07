import { getAddress } from "ethers";

const REQUIRED_CONTRACTS = [
  "TokoinFixedSupply",
  "TokoinResearchRewards",
  "AgoraAgentIdentity",
];

export function validateDeploymentReceipt(receipt) {
  const errors = [];
  if (receipt?.schema !== "agora.tokoin.base_sepolia_deployment_receipt.v1") {
    errors.push("receipt_schema_invalid");
  }
  if (receipt?.network !== "BASE_SEPOLIA" || receipt?.chain_id !== 84532) {
    errors.push("receipt_network_invalid");
  }
  if (receipt?.economic_value !== false || receipt?.mainnet_transaction !== false) {
    errors.push("receipt_scope_invalid");
  }
  if (receipt?.total_supply_aceros !== "100000000000000" || receipt?.decimals !== 8) {
    errors.push("receipt_monetary_policy_invalid");
  }
  for (const name of REQUIRED_CONTRACTS) {
    try {
      getAddress(receipt?.contracts?.[name]);
    } catch {
      errors.push(`${name}_address_invalid`);
    }
    if (!/^0x[0-9a-fA-F]{64}$/.test(String(receipt?.transactions?.[name] ?? ""))) {
      errors.push(`${name}_transaction_invalid`);
    }
    if (!Number.isSafeInteger(receipt?.block_numbers?.[name]) || receipt.block_numbers[name] < 1) {
      errors.push(`${name}_block_invalid`);
    }
  }
  for (const key of [
    "treasury_address",
    "settlement_authority_address",
    "identity_issuer_address",
  ]) {
    try {
      getAddress(receipt?.[key]);
    } catch {
      errors.push(`${key}_invalid`);
    }
  }
  return { valid: errors.length === 0, errors };
}
