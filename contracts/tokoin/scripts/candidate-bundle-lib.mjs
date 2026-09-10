import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

export const DEPLOYABLE_CONTRACTS = [
  "TokoinFixedSupply",
  "TokoinResearchRewards",
  "AgoraAgentIdentity",
];

const SOURCE_FILES = [
  "contracts/AgoraAgentIdentity.sol",
  "contracts/TokoinControlPlane.sol",
  "contracts/TokoinFixedSupply.sol",
  "contracts/TokoinResearchRewards.sol",
];

export function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => (
      `${JSON.stringify(key)}:${canonicalJson(value[key])}`
    )).join(",")}}`;
  }
  return JSON.stringify(value);
}

export function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function hashFile(root, relativePath) {
  return sha256(fs.readFileSync(path.join(root, relativePath)));
}

function artifactPath(contractName) {
  return `artifacts/contracts/${contractName}.sol/${contractName}.json`;
}

export function buildCandidateBundle(root) {
  const packageJson = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));
  const contracts = {};
  for (const contractName of DEPLOYABLE_CONTRACTS) {
    const relativeArtifact = artifactPath(contractName);
    const artifact = JSON.parse(fs.readFileSync(path.join(root, relativeArtifact), "utf8"));
    contracts[contractName] = {
      source: `contracts/${contractName}.sol`,
      artifact: relativeArtifact,
      abi_sha256: sha256(canonicalJson(artifact.abi)),
      creation_bytecode_sha256: sha256(artifact.bytecode),
      deployed_bytecode_sha256: sha256(artifact.deployedBytecode),
    };
  }

  const payload = {
    schema: "agora.tokoin.contract_release_bundle.v1",
    status: "UNDEPLOYED_AUDIT_CANDIDATE",
    target: {
      network: "BASE_SEPOLIA",
      chain_id: 84532,
      economic_value: false,
      mainnet_authorized: false,
    },
    monetary_policy: {
      name: "TOKOIN",
      symbol: "TOKOIN",
      decimals: 8,
      total_supply_aceros: "100000000000000",
      mintable_after_genesis: false,
    },
    toolchain: {
      solidity: packageJson.devDependencies.solc,
      hardhat: packageJson.devDependencies.hardhat,
      ethers: packageJson.devDependencies.ethers,
      openzeppelin: packageJson.dependencies["@openzeppelin/contracts"],
      evm_version: "cancun",
    },
    source_files: Object.fromEntries(
      SOURCE_FILES.map((relativePath) => [relativePath, hashFile(root, relativePath)]),
    ),
    build_inputs: {
      "hardhat.config.js": hashFile(root, "hardhat.config.js"),
      "package-lock.json": hashFile(root, "package-lock.json"),
      "package.json": hashFile(root, "package.json"),
      "scripts/build-candidate-bundle.mjs": hashFile(root, "scripts/build-candidate-bundle.mjs"),
      "scripts/candidate-bundle-lib.mjs": hashFile(root, "scripts/candidate-bundle-lib.mjs"),
      "scripts/static-audit.mjs": hashFile(root, "scripts/static-audit.mjs"),
      ...Object.fromEntries([
        "scripts/deploy-base-sepolia.mjs",
        "scripts/deployment-verifier-lib.mjs",
        "scripts/verify-base-sepolia.mjs",
        "scripts/release-preflight-lib.mjs",
        "scripts/release-preflight.mjs",
        "scripts/verify-candidate-bundle.mjs",
      ].map((file) => [file, hashFile(root, file)])),
    },
    contracts,
    trust_boundaries: [
      "Base and Ethereum provide public-chain consensus",
      "an external audit is required before deployment",
      "treasury, settlement authority and identity issuer must be authorized 2-of-3 Safe addresses",
      "research adjudication selects reward recipients but does not prove factual truth",
      "settlements expire and release only unclaimed reservations; roots stay immutable",
      "claim pause and preclaim cancellation are controlled by the settlement Safe",
    ],
  };
  return { ...payload, bundle_sha256: sha256(canonicalJson(payload)) };
}

export function validateCandidateBundle(bundle) {
  if (!bundle || bundle.schema !== "agora.tokoin.contract_release_bundle.v1") return false;
  const { bundle_sha256: expected, ...payload } = bundle;
  return /^[0-9a-f]{64}$/.test(String(expected ?? ""))
    && sha256(canonicalJson(payload)) === expected;
}
