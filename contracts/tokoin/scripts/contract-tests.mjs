import assert from "node:assert/strict";
import { network } from "hardhat";

import { buildSettlementBundle } from "./settlement-bundle-lib.mjs";

const { ethers } = await network.create();
const [treasury, researcher, outsider] = await ethers.getSigners();
const supply = 100_000_000_000_000n;
const oneTokoin = 100_000_000n;

const token = await ethers.deployContract("TokoinFixedSupply", [treasury.address]);
await token.waitForDeployment();
assert.equal(await token.totalSupply(), supply);
assert.equal(await token.balanceOf(treasury.address), supply);
assert.equal(await token.decimals(), 8n);

const rewards = await ethers.deployContract("TokoinResearchRewards", [
  await token.getAddress(),
  treasury.address,
]);
await rewards.waitForDeployment();
await (await token.transfer(await rewards.getAddress(), oneTokoin)).wait();

const challengeId = ethers.id("AGORA-RESEARCH-CHALLENGE-TEST-01");
const knowledgeRoot = ethers.id("ipfs-or-artifact-paper-root");
const role = ethers.encodeBytes32String("resolver");
const leaf = await rewards.claimLeaf(challengeId, researcher.address, oneTokoin, role);

await assert.rejects(
  rewards.connect(outsider).publishSettlement(challengeId, leaf, knowledgeRoot, oneTokoin),
  /AuthorityOnly/,
);
await (await rewards.publishSettlement(challengeId, leaf, knowledgeRoot, oneTokoin)).wait();
assert.equal(await rewards.reservedAmount(), oneTokoin);
await assert.rejects(
  rewards.publishSettlement(ethers.id("OVERCOMMITTED"), leaf, knowledgeRoot, oneTokoin),
  /SettlementExceedsBalance/,
);
await assert.rejects(
  rewards.publishSettlement(challengeId, leaf, knowledgeRoot, oneTokoin),
  /SettlementAlreadyPublished/,
);
await assert.rejects(
  rewards.claim(challengeId, outsider.address, oneTokoin, role, []),
  /InvalidProof/,
);
await (await rewards.claim(challengeId, researcher.address, oneTokoin, role, [])).wait();
assert.equal(await token.balanceOf(researcher.address), oneTokoin);
assert.equal(await token.totalSupply(), supply);
assert.equal(await rewards.reservedAmount(), 0n);
await assert.rejects(
  rewards.claim(challengeId, researcher.address, oneTokoin, role, []),
  /AlreadyClaimed/,
);

const secondRewards = await ethers.deployContract("TokoinResearchRewards", [
  await token.getAddress(),
  treasury.address,
]);
await secondRewards.waitForDeployment();
await (await token.transfer(await secondRewards.getAddress(), oneTokoin)).wait();
await (await secondRewards.publishSettlement(challengeId, leaf, knowledgeRoot, oneTokoin)).wait();
await assert.rejects(
  secondRewards.claim(challengeId, researcher.address, oneTokoin, role, []),
  /InvalidProof/,
);

const multiRewards = await ethers.deployContract("TokoinResearchRewards", [
  await token.getAddress(),
  treasury.address,
]);
await multiRewards.waitForDeployment();
await (await token.transfer(await multiRewards.getAddress(), oneTokoin)).wait();
const multiBundle = buildSettlementBundle({
  chain_id: 31337,
  rewards_contract_address: await multiRewards.getAddress(),
  challenge_id: "MULTI-CLAIM-01",
  knowledge_root: ethers.id("multi-claim-paper"),
  allocations: [
    { account: researcher.address, amount_aceros: "60000000", role: "resolver" },
    { account: outsider.address, amount_aceros: "40000000", role: "contributor" },
  ],
});
await (await multiRewards.publishSettlement(
  multiBundle.challenge_id,
  multiBundle.payout_root,
  multiBundle.knowledge_root,
  multiBundle.total_amount_aceros,
)).wait();
for (const allocation of multiBundle.allocations) {
  await (await multiRewards.claim(
    multiBundle.challenge_id,
    allocation.account,
    allocation.amount_aceros,
    allocation.role,
    allocation.proof,
  )).wait();
}
assert.equal(await token.balanceOf(researcher.address), 160_000_000n);
assert.equal(await token.balanceOf(outsider.address), 40_000_000n);

const identity = await ethers.deployContract("AgoraAgentIdentity", [treasury.address]);
await identity.waitForDeployment();
const agentIdentityHash = ethers.id("agora-world|agent-001");
const genesisHash = ethers.id("agent-genesis-event-001");
const tokenId = BigInt(agentIdentityHash);
await (await identity.mint(researcher.address, agentIdentityHash, genesisHash)).wait();
assert.equal(await identity.ownerOf(tokenId), researcher.address);
assert.equal(await identity.locked(tokenId), true);
await assert.rejects(
  identity.mint(outsider.address, agentIdentityHash, genesisHash),
  /IdentityAlreadyMinted/,
);
await assert.rejects(
  identity.connect(researcher).transferFrom(researcher.address, outsider.address, tokenId),
  /Soulbound/,
);
await (await identity.revoke(tokenId, ethers.id("agent device compromise"))).wait();
assert.equal(await identity.revoked(tokenId), true);

console.log(JSON.stringify({
  ok: true,
  network: "hardhatOp",
  invariants: [
    "fixed_supply",
    "eight_decimals",
    "authority_only_settlement",
    "immutable_challenge_root",
    "invalid_proof_rejected",
    "claim_replay_rejected",
    "claim_cross_deployment_replay_rejected",
    "multi_leaf_settlement_bundle_compatible",
    "settlement_overcommit_rejected",
    "reward_transfer_does_not_mint",
    "agent_identity_unique",
    "agent_identity_non_transferable",
    "agent_identity_revocable_without_erasure",
  ],
}));
