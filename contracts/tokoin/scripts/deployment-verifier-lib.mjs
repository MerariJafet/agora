import assert from "node:assert/strict";

import { Contract, ZeroAddress, getAddress } from "ethers";

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

// Interface checks establish observable governance, not Safe implementation provenance.
export async function verifyControlGovernance(provider, addresses, {
  contractFactory = (address) => new Contract(address, [
    "function getThreshold() view returns (uint256)",
    "function getOwners() view returns (address[])",
  ], provider),
} = {}) {
  // Query the RPC directly: staticNetwork can otherwise merely echo its configured chain.
  assert.equal(BigInt(await provider.send("eth_chainId", [])), 84532n, "unexpected RPC chain");
  const controls = addresses.map((address) => getAddress(address));
  assert.equal(new Set(controls).size, 3, "three distinct control addresses required");
  assert.equal(controls.length, 3, "three control roles required");
  const evidence = [];
  const blockTag = await provider.getBlockNumber();
  for (const address of controls) {
    assert.notEqual(address, ZeroAddress, "zero control address");
    assert.notEqual(await provider.getCode(address, blockTag), "0x", "control has no deployed code");
    const control = contractFactory(address);
    const threshold = await control.getThreshold({ blockTag });
    const owners = (await control.getOwners({ blockTag })).map((owner) => getAddress(owner));
    assert.equal(threshold, 2n, "control threshold must be two");
    assert.equal(owners.length, 3, "control must have three owners");
    assert.equal(new Set(owners).size, 3, "control owners must be distinct");
    assert.ok(!owners.includes(ZeroAddress), "control owner cannot be zero");
    evidence.push({ address, threshold: 2, owners, block_number: blockTag });
  }
  return evidence;
}
