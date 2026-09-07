import fs from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const token = fs.readFileSync(path.join(root, "contracts", "TokoinFixedSupply.sol"), "utf8");
const identity = fs.readFileSync(path.join(root, "contracts", "AgoraAgentIdentity.sol"), "utf8");
const rewards = fs.readFileSync(path.join(root, "contracts", "TokoinResearchRewards.sol"), "utf8");
const forbidden = [
  "ERC20Burnable",
  "Pausable",
  "ERC20Permit",
  "ERC20Votes",
  "Ownable",
  "UUPSUpgradeable",
  "TransparentUpgradeableProxy",
  "delegatecall",
  "function mint",
  "function burn",
];
const failures = forbidden.filter((needle) => token.includes(needle));
if (!token.includes("@openzeppelin/contracts/token/ERC20/ERC20.sol")) {
  failures.push("missing OpenZeppelin ERC20 import");
}
if (!token.includes("TOTAL_SUPPLY_ACEROS = 100000000000000")) {
  failures.push("wrong total supply");
}
if (!token.includes("TOKOIN_DECIMALS = 8")) {
  failures.push("wrong decimals");
}
for (const required of [
  "contract AgoraAgentIdentity is ERC721, IERC5192",
  "if (_ownerOf(tokenId) != address(0)) revert Soulbound()",
]) {
  if (!identity.includes(required)) {
    failures.push(`identity contract missing: ${required}`);
  }
}
for (const forbiddenIdentity of ["function transferFrom", "function safeTransferFrom", "delegatecall"]){
  if (identity.includes(forbiddenIdentity)) failures.push(`identity contract forbidden: ${forbiddenIdentity}`);
}
for (const required of [
  "contract TokoinResearchRewards",
  "MerkleProof.verifyCalldata",
  "block.chainid, address(this), challengeId, account, amount, role",
  "reservedAmount += totalAmount",
  "reservedAmount -= amount",
  "revert SettlementAlreadyPublished()",
  "revert ZeroAmount()",
  "function releaseExpiredSettlement",
  "function cancelSettlement",
  "function setClaimsPaused",
]) {
  if (!rewards.includes(required)) failures.push(`reward contract missing: ${required}`);
}
for (const forbiddenReward of ["function mint", "delegatecall", "selfdestruct", "tx.origin"]) {
  if (rewards.includes(forbiddenReward)) failures.push(`reward contract forbidden: ${forbiddenReward}`);
}
if (failures.length) {
  console.error(JSON.stringify({ ok: false, failures }, null, 2));
  process.exit(1);
}
console.log(JSON.stringify({
  ok: true,
  contracts: ["TokoinFixedSupply", "AgoraAgentIdentity", "TokoinResearchRewards"],
  identity_standard: "ERC-721 + ERC-5192 locked mirror",
  openzeppelin: "5.6.1",
  solc: "0.8.30"
}));
