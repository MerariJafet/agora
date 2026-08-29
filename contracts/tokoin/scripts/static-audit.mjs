import fs from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const token = fs.readFileSync(path.join(root, "contracts", "TokoinFixedSupply.sol"), "utf8");
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
if (failures.length) {
  console.error(JSON.stringify({ ok: false, failures }, null, 2));
  process.exit(1);
}
console.log(JSON.stringify({ ok: true, contract: "TokoinFixedSupply", openzeppelin: "5.6.1", solc: "0.8.30" }));
