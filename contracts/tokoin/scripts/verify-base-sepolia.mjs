import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

import { Contract, JsonRpcProvider } from "ethers";

import { validateDeploymentReceipt } from "./deployment-verifier-lib.mjs";

const root = path.resolve(import.meta.dirname, "..");
const receiptPath = path.resolve(root, "../../deployments/tokoin-testnet/base-sepolia-receipt.json");
const receipt = JSON.parse(fs.readFileSync(receiptPath, "utf8"));
assert.deepEqual(validateDeploymentReceipt(receipt), { valid: true, errors: [] });

const rpcUrl = process.env.BASE_SEPOLIA_RPC_URL;
if (!rpcUrl) throw new Error("BASE_SEPOLIA_RPC_URL is required for read-only verification");
const provider = new JsonRpcProvider(rpcUrl, 84532, { staticNetwork: true });
assert.equal(Number((await provider.getNetwork()).chainId), 84532);

function artifact(contractName) {
  return JSON.parse(fs.readFileSync(
    path.join(root, `artifacts/contracts/${contractName}.sol/${contractName}.json`),
    "utf8",
  ));
}

for (const [name, address] of Object.entries(receipt.contracts)) {
  assert.notEqual(await provider.getCode(address), "0x", `${name} has no deployed code`);
  const transactionReceipt = await provider.getTransactionReceipt(receipt.transactions[name]);
  assert.equal(transactionReceipt?.status, 1, `${name} deployment transaction failed or is missing`);
  assert.equal(transactionReceipt?.contractAddress?.toLowerCase(), address.toLowerCase());
}

const token = new Contract(receipt.contracts.TokoinFixedSupply, artifact("TokoinFixedSupply").abi, provider);
const rewards = new Contract(
  receipt.contracts.TokoinResearchRewards,
  artifact("TokoinResearchRewards").abi,
  provider,
);
const identity = new Contract(
  receipt.contracts.AgoraAgentIdentity,
  artifact("AgoraAgentIdentity").abi,
  provider,
);
assert.equal(await token.totalSupply(), 100_000_000_000_000n);
assert.equal(await token.decimals(), 8n);
assert.equal((await token.genesisTreasury()).toLowerCase(), receipt.treasury_address.toLowerCase());
assert.equal((await rewards.tokoin()).toLowerCase(), receipt.contracts.TokoinFixedSupply.toLowerCase());
assert.equal(
  (await rewards.settlementAuthority()).toLowerCase(),
  receipt.settlement_authority_address.toLowerCase(),
);
assert.equal((await identity.issuer()).toLowerCase(), receipt.identity_issuer_address.toLowerCase());

console.log(JSON.stringify({
  ok: true,
  network: "BASE_SEPOLIA",
  chain_id: 84532,
  contracts: receipt.contracts,
  read_only: true,
}));
