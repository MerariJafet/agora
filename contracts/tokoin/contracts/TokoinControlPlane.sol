// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

/// @notice Minimal interfaces/events for the MAGNA Sprint 04 local-devnet control plane.
/// @dev The production authority model is intentionally human-ratification gated.
library TokoinControlPlane {
    uint256 internal constant ONE_TOKOIN_ACEROS = 100000000;

    event ReservationRequested(bytes32 indexed challengeId, bytes32 indexed idempotencyKey);
    event ReservationReserved(bytes32 indexed challengeId, uint256 amount);
    event SettlementAllocated(bytes32 indexed challengeId, bytes32 indexed settlementPlanHash);
    event KnowledgeRootAnchored(bytes32 indexed worldInstanceId, bytes32 indexed merkleRoot);

    struct RoleCap {
        bytes32 role;
        uint256 cap;
    }

    function roleCaps() internal pure returns (RoleCap[5] memory caps) {
        caps[0] = RoleCap("proposer", 1000000);
        caps[1] = RoleCap("contributors", 59000000);
        caps[2] = RoleCap("independent_replication", 25000000);
        caps[3] = RoleCap("review_and_adjudication", 10000000);
        caps[4] = RoleCap("data_tools_infrastructure", 5000000);
    }
}
