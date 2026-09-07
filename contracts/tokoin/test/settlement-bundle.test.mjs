import assert from "node:assert/strict";
import test from "node:test";

import {
  buildSettlementBundle,
  verifyMerkleProof,
} from "../scripts/settlement-bundle-lib.mjs";

const base = {
  chain_id: 84532,
  rewards_contract_address: `0x${"12".repeat(20)}`,
  challenge_id: "research-01",
  knowledge_root: `0x${"ab".repeat(32)}`,
  allocations: [
    { account: `0x${"21".repeat(20)}`, amount_aceros: "89000000", role: "resolver" },
    { account: `0x${"22".repeat(20)}`, amount_aceros: "10000000", role: "contributor" },
    { account: `0x${"23".repeat(20)}`, amount_aceros: "1000000", role: "proposer" },
  ],
};

test("builds deterministic OpenZeppelin-compatible proofs", () => {
  const bundle = buildSettlementBundle(base);
  assert.equal(bundle.total_amount_aceros, "100000000");
  for (const allocation of bundle.allocations) {
    assert.equal(verifyMerkleProof(allocation.leaf, allocation.proof, bundle.payout_root), true);
  }
  const reversed = buildSettlementBundle({ ...base, allocations: [...base.allocations].reverse() });
  assert.deepEqual(reversed, bundle);
});

test("rejects over-allocation and unsupported chains", () => {
  assert.throws(
    () => buildSettlementBundle({
      ...base,
      allocations: [{ ...base.allocations[0], amount_aceros: "100000001" }],
    }),
    /exceeds one TOKOIN/,
  );
  assert.throws(() => buildSettlementBundle({ ...base, chain_id: 1 }), /only local devnet/);
});

test("rejects duplicate claims", () => {
  assert.throws(
    () => buildSettlementBundle({
      ...base,
      allocations: [base.allocations[0], base.allocations[0]],
    }),
    /duplicate allocation leaf/,
  );
});
