// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @notice TOKOIN testnet token. No economic value, no mainnet deployment.
/// @dev Minimal non-upgradeable ERC-20: no owner, no mint function after constructor,
/// no burn extension, no pause extension, no permit, no votes and no fee logic.
contract TokoinFixedSupply is ERC20 {
    uint8 private constant TOKOIN_DECIMALS = 8;
    uint256 public constant TOTAL_SUPPLY_ACEROS = 100000000000000;
    address public immutable genesisTreasury;

    error ZeroTreasury();

    constructor(address genesisTreasury_) ERC20("TOKOIN", "TOKOIN") {
        if (genesisTreasury_ == address(0)) {
            revert ZeroTreasury();
        }
        genesisTreasury = genesisTreasury_;
        _mint(genesisTreasury_, TOTAL_SUPPLY_ACEROS);
    }

    function decimals() public pure override returns (uint8) {
        return TOKOIN_DECIMALS;
    }
}
