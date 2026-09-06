// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import {IERC165} from "@openzeppelin/contracts/utils/introspection/IERC165.sol";

/// @dev Minimal ERC-5192 interface for locked, non-transferable ERC-721 tokens.
interface IERC5192 is IERC165 {
    event Locked(uint256 tokenId);
    event Unlocked(uint256 tokenId);

    function locked(uint256 tokenId) external view returns (bool);
}

/// @notice Optional public mirror of an AGORA AgentGenesis identity.
/// @dev This contract is not deployed by the repository and never grants AGORA
/// permissions. The existing Ed25519 genesis/device system remains authoritative.
contract AgoraAgentIdentity is ERC721, IERC5192 {
    address public immutable issuer;
    mapping(bytes32 agentIdentityHash => bool minted) public identityMinted;
    mapping(uint256 tokenId => bytes32 genesisHash) public genesisHashes;
    mapping(uint256 tokenId => bool revoked) public revoked;

    error IssuerOnly();
    error IdentityAlreadyMinted();
    error Soulbound();

    event IdentityRevoked(uint256 indexed tokenId, bytes32 indexed reasonHash);

    constructor(address issuer_) ERC721("AGORA Agent Identity", "AGORA-ID") {
        if (issuer_ == address(0)) revert IssuerOnly();
        issuer = issuer_;
    }

    function mint(address to, bytes32 agentIdentityHash, bytes32 genesisHash)
        external
        returns (uint256 tokenId)
    {
        if (msg.sender != issuer) revert IssuerOnly();
        if (identityMinted[agentIdentityHash]) revert IdentityAlreadyMinted();
        identityMinted[agentIdentityHash] = true;
        tokenId = uint256(agentIdentityHash);
        genesisHashes[tokenId] = genesisHash;
        _safeMint(to, tokenId);
        emit Locked(tokenId);
    }

    function revoke(uint256 tokenId, bytes32 reasonHash) external {
        if (msg.sender != issuer) revert IssuerOnly();
        _requireOwned(tokenId);
        revoked[tokenId] = true;
        emit IdentityRevoked(tokenId, reasonHash);
    }

    function locked(uint256 tokenId) external view returns (bool) {
        _requireOwned(tokenId);
        return true;
    }

    function approve(address, uint256) public pure override {
        revert Soulbound();
    }

    function setApprovalForAll(address, bool) public pure override {
        revert Soulbound();
    }

    function _update(address to, uint256 tokenId, address auth)
        internal
        override
        returns (address)
    {
        if (_ownerOf(tokenId) != address(0)) revert Soulbound();
        return super._update(to, tokenId, auth);
    }

    function supportsInterface(bytes4 interfaceId) public view override(ERC721, IERC165) returns (bool) {
        return interfaceId == type(IERC5192).interfaceId || super.supportsInterface(interfaceId);
    }
}
