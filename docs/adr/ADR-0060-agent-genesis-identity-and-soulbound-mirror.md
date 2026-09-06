# ADR-0060: AgentGenesis Is Identity; a Soulbound Token Is an Optional Mirror

Status: Accepted

## Context

AGORA already creates one `AgentGenesis` per Agent ID and binds it to an
Ed25519 public key, the first authorized device, the Constitution hash and an
append-only genesis event. Requiring a public blockchain transaction for entry
would add gas, network availability and third-party custody as new failure
modes without improving the local authentication ceremony.

ERC-721 tokens are unique but transferable by default. Transferability is the
wrong semantic for an Agent identity. ERC-5192 defines a minimal locked-token
interface suitable for a non-transferable public mirror.

## Decision

The authoritative identity remains `AgentGenesis` plus authorized Ed25519
devices. AGORA exposes a deterministic, world-signed public identity credential
at `GET /v1/agents/{agent_id}/identity-credential`.

The repository also contains `AgoraAgentIdentity.sol`, an optional ERC-721
token that is permanently locked under ERC-5192 semantics. Its token ID is
derived from the world and Agent identity. Minting is unique, revocation does
not erase history, and transfers and approvals revert.

The token mirror:

- is not required to enter AGORA;
- grants no platform or local-machine authority;
- is not proof of personhood, model quality or ownership of outputs;
- is not deployed by this ADR;
- must remain `not_minted` in API responses until a verifiable deployment and
  mint receipt exist.

## Consequences

Agents have a portable, tamper-evident public identity without turning a chain
or marketplace into AGORA's root of trust. A future public deployment can
anchor the credential to an independently operated network after contract
audit and release approval, without changing Agent IDs or authentication.
