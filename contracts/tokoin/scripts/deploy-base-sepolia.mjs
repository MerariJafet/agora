import fs from "node:fs";
import path from "node:path";
import { network } from "hardhat";
import { evaluatePublicTestnetReadiness, repoRoot } from "./release-preflight-lib.mjs";

import { verifyControlGovernance } from "./deployment-verifier-lib.mjs";

const readiness = evaluatePublicTestnetReadiness();
if (!readiness.ready) throw new Error(`release preflight failed: ${readiness.blockers.join(",")}`);

const { ethers } = await network.create();
const chainId = Number((await ethers.provider.getNetwork()).chainId);
if (chainId !== 84532) throw new Error(`refusing unexpected chain ${chainId}`);

const treasury = process.env.TOKOIN_GENESIS_TREASURY_ADDRESS;
const settlementAuthority = process.env.TOKOIN_SETTLEMENT_AUTHORITY_ADDRESS;
const identityIssuer = process.env.AGORA_IDENTITY_ISSUER_ADDRESS;
const controlGovernance = await verifyControlGovernance(ethers.provider, [
  treasury, settlementAuthority, identityIssuer,
]);
const token = await ethers.deployContract("TokoinFixedSupply", [treasury]);
await token.waitForDeployment();
const tokenReceipt = await token.deploymentTransaction().wait(2);
const tokenAddress = await token.getAddress();
const rewards = await ethers.deployContract("TokoinResearchRewards", [
  tokenAddress,
  settlementAuthority,
]);
await rewards.waitForDeployment();
const rewardsReceipt = await rewards.deploymentTransaction().wait(2);
const identity = await ethers.deployContract("AgoraAgentIdentity", [identityIssuer]);
await identity.waitForDeployment();
const identityReceipt = await identity.deploymentTransaction().wait(2);

if ((await token.totalSupply()) !== 100_000_000_000_000n) {
  throw new Error("deployed supply mismatch");
}
if ((await token.balanceOf(treasury)) !== 100_000_000_000_000n) {
  throw new Error("treasury allocation mismatch");
}
if ((await rewards.settlementAuthority()).toLowerCase() !== settlementAuthority.toLowerCase()) {
  throw new Error("settlement authority mismatch");
}
if ((await identity.issuer()).toLowerCase() !== identityIssuer.toLowerCase()) {
  throw new Error("identity issuer mismatch");
}

const output = {
  schema: "agora.tokoin.base_sepolia_deployment_receipt.v1",
  network: "BASE_SEPOLIA",
  chain_id: chainId,
  economic_value: false,
  control_governance: controlGovernance,
  contracts: {
    TokoinFixedSupply: tokenAddress,
    TokoinResearchRewards: await rewards.getAddress(),
    AgoraAgentIdentity: await identity.getAddress(),
  },
  treasury_address: treasury,
  settlement_authority_address: settlementAuthority,
  identity_issuer_address: identityIssuer,
  transactions: {
    TokoinFixedSupply: tokenReceipt.hash,
    TokoinResearchRewards: rewardsReceipt.hash,
    AgoraAgentIdentity: identityReceipt.hash,
  },
  block_numbers: {
    TokoinFixedSupply: tokenReceipt.blockNumber,
    TokoinResearchRewards: rewardsReceipt.blockNumber,
    AgoraAgentIdentity: identityReceipt.blockNumber,
  },
  confirmations_required: 2,
  total_supply_aceros: "100000000000000",
  decimals: 8,
  mainnet_transaction: false,
  automatic_funding_or_minting_after_deployment: false,
};
const receiptPath = path.join(repoRoot, "deployments/tokoin-testnet/base-sepolia-receipt.json");
fs.writeFileSync(receiptPath, `${JSON.stringify(output, null, 2)}\n`, { flag: "wx" });
console.log(JSON.stringify(output, null, 2));
