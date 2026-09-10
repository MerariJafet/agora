import assert from "node:assert/strict";
import test from "node:test";

import { validateDeploymentReceipt, verifyControlGovernance } from "../scripts/deployment-verifier-lib.mjs";

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

const controls = [valid.treasury_address, valid.settlement_authority_address, valid.identity_issuer_address];
function governanceFixture({ chain = "0x14a34", code = "0x1234", threshold = 2n, owners = controls } = {}) {
  return {
    provider: {
      send: async (method) => { assert.equal(method, "eth_chainId"); return chain; },
      getBlockNumber: async () => 123,
      getCode: async (_address, blockTag) => { assert.equal(blockTag, 123); return code; },
    },
    options: { contractFactory: () => ({
      getThreshold: async ({ blockTag }) => { assert.equal(blockTag, 123); return threshold; },
      getOwners: async ({ blockTag }) => { assert.equal(blockTag, 123); return owners; },
    }) },
  };
}
test("reads governance for all three roles at one block", async () => {
  const { provider, options } = governanceFixture();
  const evidence = await verifyControlGovernance(provider, controls, options);
  assert.equal(evidence.length, 3);
  assert.equal(evidence[2].threshold, 2);
  assert.equal(evidence[2].block_number, 123);
});
for (const [name, override, reason] of [
  ["wrong RPC chain", { chain: "0x2105" }, /unexpected RPC chain/],
  ["EOA", { code: "0x" }, /no deployed code/],
  ["one-of-three", { threshold: 1n }, /threshold must be two/],
  ["two-of-four", { owners: [...controls, valid.contracts.TokoinFixedSupply] }, /three owners/],
  ["duplicate owners", { owners: [controls[0], controls[0], controls[1]] }, /distinct/],
  ["zero owner", { owners: [controls[0], controls[1], `0x${"00".repeat(20)}`] }, /cannot be zero/],
]) {
  test(`rejects ${name}`, async () => {
    const { provider, options } = governanceFixture(override);
    await assert.rejects(verifyControlGovernance(provider, controls, options), reason);
  });
}
test("rejects concentrated controls and unavailable RPC", async () => {
  const { provider, options } = governanceFixture();
  await assert.rejects(verifyControlGovernance(provider, [controls[0], controls[0], controls[1]], options), /distinct/);
  provider.send = async () => { throw new Error("RPC offline"); };
  await assert.rejects(verifyControlGovernance(provider, controls, options), /RPC offline/);
});
