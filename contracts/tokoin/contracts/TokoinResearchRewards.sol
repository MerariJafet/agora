// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {MerkleProof} from "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";

/// @notice Distributes pre-funded TOKOIN from immutable research settlements.
/// @dev The settlement authority must be a separately governed multisig. It
/// attests that AGORA's off-chain research process reached its published
/// criteria; this contract does not pretend popularity or signatures prove truth.
contract TokoinResearchRewards {
    using SafeERC20 for IERC20;

    struct Settlement {
        bytes32 payoutRoot;
        bytes32 knowledgeRoot;
        uint256 totalAmount;
        uint256 claimedAmount;
    }

    IERC20 public immutable tokoin;
    address public immutable settlementAuthority;
    uint256 public reservedAmount;

    mapping(bytes32 challengeId => Settlement settlement) public settlements;
    mapping(bytes32 claimId => bool claimed) public claims;

    error AuthorityOnly();
    error ZeroAddress();
    error EmptyRoot();
    error SettlementAlreadyPublished();
    error SettlementExceedsBalance();
    error InvalidProof();
    error AlreadyClaimed();

    event SettlementPublished(
        bytes32 indexed challengeId,
        bytes32 indexed payoutRoot,
        bytes32 indexed knowledgeRoot,
        uint256 totalAmount
    );
    event RewardClaimed(
        bytes32 indexed challengeId,
        address indexed account,
        bytes32 indexed role,
        uint256 amount
    );

    constructor(IERC20 tokoin_, address settlementAuthority_) {
        if (address(tokoin_) == address(0) || settlementAuthority_ == address(0)) {
            revert ZeroAddress();
        }
        tokoin = tokoin_;
        settlementAuthority = settlementAuthority_;
    }

    function publishSettlement(
        bytes32 challengeId,
        bytes32 payoutRoot,
        bytes32 knowledgeRoot,
        uint256 totalAmount
    ) external {
        if (msg.sender != settlementAuthority) revert AuthorityOnly();
        if (payoutRoot == bytes32(0) || knowledgeRoot == bytes32(0)) revert EmptyRoot();
        if (settlements[challengeId].payoutRoot != bytes32(0)) {
            revert SettlementAlreadyPublished();
        }
        uint256 balance = tokoin.balanceOf(address(this));
        if (totalAmount == 0 || reservedAmount > balance || totalAmount > balance - reservedAmount) {
            revert SettlementExceedsBalance();
        }
        settlements[challengeId] = Settlement({
            payoutRoot: payoutRoot,
            knowledgeRoot: knowledgeRoot,
            totalAmount: totalAmount,
            claimedAmount: 0
        });
        reservedAmount += totalAmount;
        emit SettlementPublished(challengeId, payoutRoot, knowledgeRoot, totalAmount);
    }

    function claim(
        bytes32 challengeId,
        address account,
        uint256 amount,
        bytes32 role,
        bytes32[] calldata proof
    ) external {
        if (account == address(0)) revert ZeroAddress();
        Settlement storage settlement = settlements[challengeId];
        bytes32 claimId = keccak256(abi.encode(challengeId, account, amount, role));
        if (claims[claimId]) revert AlreadyClaimed();

        bytes32 leaf = keccak256(bytes.concat(keccak256(abi.encode(
            challengeId, account, amount, role
        ))));
        if (!MerkleProof.verifyCalldata(proof, settlement.payoutRoot, leaf)) {
            revert InvalidProof();
        }
        if (settlement.claimedAmount + amount > settlement.totalAmount) {
            revert SettlementExceedsBalance();
        }

        claims[claimId] = true;
        settlement.claimedAmount += amount;
        reservedAmount -= amount;
        tokoin.safeTransfer(account, amount);
        emit RewardClaimed(challengeId, account, role, amount);
    }
}
