import assert from "node:assert/strict";
import test from "node:test";

import { validateDeploymentReceipt } from "../scripts/deployment-verifier-lib.mjs";

const valid = {
  schema: "agora.tokoin.base_sepolia_deployment_receipt.v1",
  network: "BASE_SEPOLIA",
  chain_id: 84532,
  economic_value: false,
  contracts: {
    TokoinFixedSupply: `0x${"11".repeat(20)}`,
    TokoinResearchRewards: `0x${"22".repeat(20)}`,
    AgoraAgentIdentity: `0x${"33".repeat(20)}`,
  },
  treasury_address: `0x${"44".repeat(20)}`,
  settlement_authority_address: `0x${"55".repeat(20)}`,
  identity_issuer_address: `0x${"66".repeat(20)}`,
  transactions: {
    TokoinFixedSupply: `0x${"aa".repeat(32)}`,
    TokoinResearchRewards: `0x${"bb".repeat(32)}`,
    AgoraAgentIdentity: `0x${"cc".repeat(32)}`,
  },
  block_numbers: {
    TokoinFixedSupply: 1,
    TokoinResearchRewards: 2,
    AgoraAgentIdentity: 3,
  },
  total_supply_aceros: "100000000000000",
  decimals: 8,
  mainnet_transaction: false,
};

test("accepts a narrow Base Sepolia no-value receipt", () => {
  assert.deepEqual(validateDeploymentReceipt(valid), { valid: true, errors: [] });
});

test("rejects mainnet scope, missing transactions and invalid addresses", () => {
  const result = validateDeploymentReceipt({
    ...valid,
    chain_id: 8453,
    economic_value: true,
    contracts: { ...valid.contracts, TokoinFixedSupply: "not-an-address" },
    transactions: { ...valid.transactions, TokoinResearchRewards: null },
  });
  assert.equal(result.valid, false);
  assert.ok(result.errors.includes("receipt_network_invalid"));
  assert.ok(result.errors.includes("receipt_scope_invalid"));
  assert.ok(result.errors.includes("TokoinFixedSupply_address_invalid"));
  assert.ok(result.errors.includes("TokoinResearchRewards_transaction_invalid"));
});
