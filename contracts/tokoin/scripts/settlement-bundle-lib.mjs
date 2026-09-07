import { AbiCoder, encodeBytes32String, getAddress, keccak256 } from "ethers";

const MAX_REWARD_ACEROS = 100_000_000n;

function bytes32(value, label) {
  if (/^0x[0-9a-fA-F]{64}$/.test(value)) return value.toLowerCase();
  if (typeof value === "string" && new TextEncoder().encode(value).length <= 31) {
    return encodeBytes32String(value);
  }
  throw new Error(`${label} must be bytes32 hex or at most 31 UTF-8 bytes`);
}

function hashPair(left, right) {
  const [a, b] = [left, right].sort();
  return keccak256(`0x${a.slice(2)}${b.slice(2)}`);
}

function leafFor({ chainId, contractAddress, challengeId, account, amount, role }) {
  const inner = keccak256(AbiCoder.defaultAbiCoder().encode(
    ["uint256", "address", "bytes32", "address", "uint256", "bytes32"],
    [chainId, contractAddress, challengeId, account, amount, role],
  ));
  return keccak256(inner);
}

function merkleLayers(leaves) {
  const layers = [leaves];
  while (layers.at(-1).length > 1) {
    const current = layers.at(-1);
    const next = [];
    for (let index = 0; index < current.length; index += 2) {
      next.push(hashPair(current[index], current[index + 1] ?? current[index]));
    }
    layers.push(next);
  }
  return layers;
}

function proofFor(layers, originalIndex) {
  const proof = [];
  let index = originalIndex;
  for (let depth = 0; depth < layers.length - 1; depth += 1) {
    const layer = layers[depth];
    const sibling = index % 2 === 0 ? index + 1 : index - 1;
    proof.push(layer[sibling] ?? layer[index]);
    index = Math.floor(index / 2);
  }
  return proof;
}

export function verifyMerkleProof(leaf, proof, root) {
  return proof.reduce((current, sibling) => hashPair(current, sibling), leaf) === root;
}

export function buildSettlementBundle(input) {
  if (!input || !Array.isArray(input.allocations) || input.allocations.length === 0) {
    throw new Error("at least one allocation is required");
  }
  const chainId = BigInt(input.chain_id);
  if (chainId !== 84532n && chainId !== 31337n) {
    throw new Error("only local devnet or Base Sepolia settlement bundles are supported");
  }
  const contractAddress = getAddress(input.rewards_contract_address);
  const challengeId = bytes32(input.challenge_id, "challenge_id");
  const knowledgeRoot = bytes32(input.knowledge_root, "knowledge_root");
  const allocations = input.allocations.map((allocation) => {
    const account = getAddress(allocation.account);
    const amount = BigInt(allocation.amount_aceros);
    if (amount <= 0n) throw new Error("allocation amount must be positive");
    const role = bytes32(allocation.role, "role");
    return {
      account,
      amount_aceros: amount.toString(),
      role,
      leaf: leafFor({ chainId, contractAddress, challengeId, account, amount, role }),
    };
  }).sort((a, b) => a.leaf.localeCompare(b.leaf));

  if (new Set(allocations.map((allocation) => allocation.leaf)).size !== allocations.length) {
    throw new Error("duplicate allocation leaf");
  }
  const total = allocations.reduce(
    (sum, allocation) => sum + BigInt(allocation.amount_aceros),
    0n,
  );
  if (total > MAX_REWARD_ACEROS) throw new Error("settlement exceeds one TOKOIN");

  const layers = merkleLayers(allocations.map((allocation) => allocation.leaf));
  const payoutRoot = layers.at(-1)[0];
  return {
    schema: "agora.tokoin.evm_settlement_bundle.v1",
    chain_id: Number(chainId),
    rewards_contract_address: contractAddress,
    challenge_id: challengeId,
    payout_root: payoutRoot,
    knowledge_root: knowledgeRoot,
    total_amount_aceros: total.toString(),
    allocations: allocations.map((allocation, index) => ({
      ...allocation,
      proof: proofFor(layers, index),
    })),
    warnings: [
      "This bundle does not authorize or publish a settlement.",
      "The knowledge root and recipient allocation require independent review.",
      "A reward is not proof that a scientific claim is true.",
    ],
  };
}
