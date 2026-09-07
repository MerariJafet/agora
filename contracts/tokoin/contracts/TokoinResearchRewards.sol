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
        uint256 releasedAmount;
        uint64 claimDeadline;
        bool cancelled;
    }

    uint64 public constant MIN_CLAIM_WINDOW = 1 days;
    uint64 public constant MAX_CLAIM_WINDOW = 365 days;

    IERC20 public immutable tokoin;
    address public immutable settlementAuthority;
    uint256 public reservedAmount;
    bool public claimsPaused;

    mapping(bytes32 challengeId => Settlement settlement) public settlements;
    mapping(bytes32 claimId => bool claimed) public claims;

    error AuthorityOnly();
    error ZeroAddress();
    error EmptyRoot();
    error SettlementAlreadyPublished();
    error SettlementExceedsBalance();
    error InvalidProof();
    error AlreadyClaimed();
    error ZeroAmount();
    error InvalidClaimDeadline();
    error ClaimsPaused();
    error SettlementExpired();
    error SettlementNotExpired();
    error SettlementInactive();
    error SettlementHasClaims();

    event SettlementPublished(
        bytes32 indexed challengeId,
        bytes32 indexed payoutRoot,
        bytes32 indexed knowledgeRoot,
        uint256 totalAmount,
        uint64 claimDeadline
    );
    event RewardClaimed(
        bytes32 indexed challengeId,
        address indexed account,
        bytes32 indexed role,
        uint256 amount
    );
    event ClaimsPauseChanged(bool paused);
    event SettlementCancelled(bytes32 indexed challengeId, uint256 releasedAmount);
    event ExpiredSettlementReleased(bytes32 indexed challengeId, uint256 releasedAmount);

    /// @notice Canonical leaf for this exact chain and contract deployment.
    /// @dev Domain separation prevents a valid allocation from being replayed
    /// on another TOKOIN deployment that accidentally publishes the same root.
    function claimLeaf(
        bytes32 challengeId,
        address account,
        uint256 amount,
        bytes32 role
    ) public view returns (bytes32) {
        return keccak256(bytes.concat(keccak256(abi.encode(
            block.chainid, address(this), challengeId, account, amount, role
        ))));
    }

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
        uint256 totalAmount,
        uint64 claimDeadline
    ) external {
        if (msg.sender != settlementAuthority) revert AuthorityOnly();
        if (payoutRoot == bytes32(0) || knowledgeRoot == bytes32(0)) revert EmptyRoot();
        if (
            claimDeadline < block.timestamp + MIN_CLAIM_WINDOW
                || claimDeadline > block.timestamp + MAX_CLAIM_WINDOW
        ) revert InvalidClaimDeadline();
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
            claimedAmount: 0,
            releasedAmount: 0,
            claimDeadline: claimDeadline,
            cancelled: false
        });
        reservedAmount += totalAmount;
        emit SettlementPublished(challengeId, payoutRoot, knowledgeRoot, totalAmount, claimDeadline);
    }

    /// @notice Pauses claims during incident response without changing roots or balances.
    function setClaimsPaused(bool paused) external {
        if (msg.sender != settlementAuthority) revert AuthorityOnly();
        claimsPaused = paused;
        emit ClaimsPauseChanged(paused);
    }

    /// @notice Cancels an incorrect settlement only before any allocation was claimed.
    /// @dev The immutable record remains. A corrected settlement must use a successor challenge ID.
    function cancelSettlement(bytes32 challengeId) external {
        if (msg.sender != settlementAuthority) revert AuthorityOnly();
        Settlement storage settlement = settlements[challengeId];
        if (settlement.payoutRoot == bytes32(0) || settlement.cancelled) {
            revert SettlementInactive();
        }
        if (settlement.claimedAmount != 0) revert SettlementHasClaims();
        uint256 remaining = settlement.totalAmount - settlement.releasedAmount;
        settlement.releasedAmount += remaining;
        settlement.cancelled = true;
        reservedAmount -= remaining;
        emit SettlementCancelled(challengeId, remaining);
    }

    /// @notice Releases an expired settlement's unclaimed reservation for future settlements.
    /// @dev Tokens remain in this contract; this function cannot withdraw or redirect them.
    function releaseExpiredSettlement(bytes32 challengeId) external {
        Settlement storage settlement = settlements[challengeId];
        if (settlement.payoutRoot == bytes32(0) || settlement.cancelled) {
            revert SettlementInactive();
        }
        if (block.timestamp <= settlement.claimDeadline) revert SettlementNotExpired();
        uint256 remaining = settlement.totalAmount - settlement.claimedAmount - settlement.releasedAmount;
        if (remaining == 0) revert SettlementInactive();
        settlement.releasedAmount += remaining;
        reservedAmount -= remaining;
        emit ExpiredSettlementReleased(challengeId, remaining);
    }

    function claim(
        bytes32 challengeId,
        address account,
        uint256 amount,
        bytes32 role,
        bytes32[] calldata proof
    ) external {
        if (claimsPaused) revert ClaimsPaused();
        if (account == address(0)) revert ZeroAddress();
        if (amount == 0) revert ZeroAmount();
        Settlement storage settlement = settlements[challengeId];
        if (settlement.payoutRoot == bytes32(0) || settlement.cancelled) {
            revert SettlementInactive();
        }
        if (block.timestamp > settlement.claimDeadline) revert SettlementExpired();
        bytes32 claimId = claimLeaf(challengeId, account, amount, role);
        if (claims[claimId]) revert AlreadyClaimed();

        if (!MerkleProof.verifyCalldata(proof, settlement.payoutRoot, claimId)) {
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
