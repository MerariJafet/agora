"""MAGNA Sprint 04 TOKOIN local-devnet control plane.

This module models the audit-ready TOKOIN testnet integration without creating
keys, touching mainnet, converting legacy balances, or pretending local state is
authoritative on-chain balance. Public testnet deployment is gated by human
ratification and independent audit.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.boundary import validate_boundary
from agora_api.config import get_settings
from agora_api.errors import Conflict, NotFound, OwnerAuthorityRequired, ValidationFailed
from agora_api.events import append_event, now_utc
from agora_api.ids import (
    new_research_reservation_id,
    new_tokoin_claimable_allocation_id,
    new_tokoin_deployment_id,
    new_tokoin_knowledge_root_anchor_id,
    new_tokoin_settlement_plan_id,
    new_tokoin_wallet_binding_id,
)
from agora_api.models import (
    Agent,
    MagnaMerkleBatch,
    MagnaResolutionReceipt,
    TokoinClaimableAllocation,
    TokoinDeploymentManifest,
    TokoinKnowledgeRootAnchor,
    TokoinReservation,
    TokoinSettlementPlan,
    TokoinWalletBinding,
)
from agora_api.provenance import SYSTEM_ACTOR_ID

TOKOIN_DECIMALS = 8
ONE_TOKOIN_ATOMIC = 100_000_000
TOTAL_SUPPLY_ATOMIC = 100_000_000_000_000
LOCAL_CHAIN_ID = 31337
BASE_SEPOLIA_CHAIN_ID = 84532
SOLIDITY_VERSION = "0.8.30"
OPENZEPPELIN_VERSION = "5.6.1"
SETTLEMENT_BACKEND = "TOKOIN_LOCAL_DEVNET_V1"
REPO_ROOT = Path(__file__).resolve().parents[3]
RATIFIED_FOUNDER_BUNDLE_PATH = (
    REPO_ROOT
    / "audit"
    / "tokoin-testnet"
    / "ratifications"
    / "founder-ratification-bundle-ratified-2026-08-29.json"
)
EXTERNAL_AUDIT_REFERENCE_PATH = (
    REPO_ROOT / "audit" / "tokoin-testnet" / "external" / "audit-report-reference.json"
)
AUDITOR_INDEPENDENCE_PATH = (
    REPO_ROOT
    / "audit"
    / "tokoin-testnet"
    / "external"
    / "auditor-independence-disclosure.json"
)
CONTRACT_RELEASE_BUNDLE_PATH = (
    REPO_ROOT
    / "audit"
    / "tokoin-testnet"
    / "release-candidate"
    / "contract-release-bundle-v1.json"
)
BASE_SEPOLIA_AUTHORIZATION_PATH = (
    REPO_ROOT
    / "audit"
    / "tokoin-testnet"
    / "release-candidate"
    / "base-sepolia-deploy-authorization.json"
)
BASE_SEPOLIA_RECEIPT_PATH = (
    REPO_ROOT / "deployments" / "tokoin-testnet" / "base-sepolia-receipt.json"
)
ROLE_CAPS = {
    "proposer": 1_000_000,
    "contributors": 59_000_000,
    "independent_replication": 25_000_000,
    "review_and_adjudication": 10_000_000,
    "data_tools_infrastructure": 5_000_000,
}


def require_local_control_plane() -> None:
    """Fail closed if simulated economic mutations reach production."""
    settings = get_settings()
    if settings.is_production or not settings.tokoin_local_control_plane_enabled:
        raise Conflict("Local TOKOIN control-plane mutations are not explicitly enabled.")


def _require_reservation_operator(row: TokoinReservation, owner_id: str) -> None:
    if row.requested_by_owner_id != owner_id:
        raise OwnerAuthorityRequired(
            "Only the Owner who initiated this TOKOIN reservation may advance it."
        )

OFFCHAIN_COMPONENTS = {
    "GenesisTreasury": (
        "Local/off-chain treasury policy placeholder; no deployed contract in Sprint 04."
    ),
    "RewardBudgetVault": "Local DB reservation/budget accounting; not trustless on-chain vault.",
    "ChallengeEscrow": (
        "Local reservation saga with deterministic placeholder address; "
        "no deployed escrow contract."
    ),
    "RewardSplitter": "Validated off-chain role-cap splitter; no deployed splitter contract.",
    "PoolEscrow": (
        "Intentionally deferred from public release claims until contract/protocol exists."
    ),
    "AgentPassportAnchor": (
        "Agent identity remains Ed25519/off-chain; no deployed EVM passport anchor."
    ),
    "KnowledgeRootRegistry": (
        "Local Merkle root anchor projection; not an on-chain registry in Sprint 04."
    ),
    "SettlementSaga": "Off-chain DB/outbox state machine; exactly-once claim is local-devnet only.",
    "WalletBinding": "Off-chain agent/controller/wallet binding; no custody, no private keys.",
}

SCOPE_MATRIX_COMPONENTS = (
    "TokoinFixedSupply",
    "GenesisTreasury",
    "RewardBudgetVault",
    "ChallengeEscrow",
    "RewardSplitter",
    "PoolEscrow",
    "AgentPassportAnchor",
    "KnowledgeRootRegistry",
    "SettlementSaga",
    "WalletBinding",
    "DeploymentScriptsAndChainGuard",
)

RATIFICATION_DECISIONS = (
    (
        "RAT-01",
        "Operator and jurisdiction",
        "Founder/operator confirms responsible operator identity and jurisdiction.",
    ),
    (
        "RAT-02",
        "Token utility rights",
        "Founder/operator confirms TOKOIN is not represented as equity, debt or guaranteed value.",
    ),
    (
        "RAT-03",
        "Genesis allocation",
        "Founder/operator ratifies genesis allocation policy before public testnet.",
    ),
    (
        "RAT-04",
        "Network",
        "Founder/operator selects the public testnet network.",
    ),
    (
        "RAT-05",
        "OPEN license",
        "Founder/operator ratifies OPEN knowledge contribution license terms.",
    ),
    (
        "RAT-06",
        "SEALED/RESTRICTED governance",
        "Founder/operator ratifies how non-OPEN knowledge lanes are excluded from public rewards.",
    ),
    (
        "RAT-07",
        "Wallet custody and recovery",
        "Founder/operator ratifies non-custodial wallet and recovery warnings.",
    ),
    (
        "RAT-08",
        "Scientific scope safety",
        "Founder/operator ratifies that rewards do not certify factual truth.",
    ),
)


def canonical_hash(payload: dict[str, Any], *, domain: str) -> str:
    raw = json.dumps(
        {"domain": domain, "payload": payload}, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _load_json_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def public_testnet_readiness_view() -> dict[str, Any]:
    """Read-only, file-backed truth about the public EVM candidate."""
    audit = _load_json_object(EXTERNAL_AUDIT_REFERENCE_PATH) or {}
    independence = _load_json_object(AUDITOR_INDEPENDENCE_PATH) or {}
    bundle = _load_json_object(CONTRACT_RELEASE_BUNDLE_PATH) or {}
    authorization = _load_json_object(BASE_SEPOLIA_AUTHORIZATION_PATH)
    deployment = _load_json_object(BASE_SEPOLIA_RECEIPT_PATH)

    bundle_hash = bundle.get("bundle_sha256")
    bundle_payload = {key: value for key, value in bundle.items() if key != "bundle_sha256"}
    calculated_bundle_hash = hashlib.sha256(
        json.dumps(bundle_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    bundle_valid = (
        bundle.get("schema") == "agora.tokoin.contract_release_bundle.v1"
        and isinstance(bundle_hash, str)
        and len(bundle_hash) == 64
        and bundle_hash == calculated_bundle_hash
    )
    independence_complete = (
        independence.get("status") == "INDEPENDENT_CONFIRMED"
        and independence.get("accepted_by_operator") is True
        and isinstance(independence.get("auditor"), str)
        and bool(independence["auditor"].strip())
        and isinstance(independence.get("relationship_disclosure"), str)
        and bool(independence["relationship_disclosure"].strip())
    )
    audit_complete = (
        audit.get("status") == "COMPLETE_PASSED"
        and audit.get("accepted_by_operator") is True
        and audit.get("critical_findings") == 0
        and audit.get("high_findings") == 0
        and bundle_valid
        and audit.get("contract_release_bundle_hash") == bundle_hash
        and isinstance(audit.get("report_hash"), str)
        and len(audit["report_hash"]) == 64
        and independence_complete
    )
    deployed = (
        deployment is not None
        and deployment.get("schema") == "agora.tokoin.base_sepolia_deployment_receipt.v1"
        and deployment.get("network") == "BASE_SEPOLIA"
        and deployment.get("chain_id") == BASE_SEPOLIA_CHAIN_ID
    )
    blockers = []
    if not bundle_valid:
        blockers.append("contract_release_bundle_missing_or_invalid")
    if not audit_complete:
        blockers.append("independent_external_audit_incomplete")
    if not independence_complete:
        blockers.append("auditor_independence_not_confirmed")
    if authorization is None:
        blockers.append("base_sepolia_authorization_absent")

    result = {
        "schema": "agora.tokoin.public_testnet_readiness.v1",
        "stage": (
            "DEPLOYED_TESTNET" if deployed else "AUDIT_CANDIDATE" if bundle_valid else "SOURCE_ONLY"
        ),
        "candidate_bundle": {
            "present": bool(bundle),
            "integrity_valid": bundle_valid,
            "bundle_sha256": bundle_hash if bundle_valid else None,
            "contracts": sorted((bundle.get("contracts") or {}).keys()) if bundle_valid else [],
        },
        "independent_audit": {
            "complete": audit_complete,
            "status": audit.get("status", "MISSING"),
            "accepted_by_operator": audit.get("accepted_by_operator") is True,
        },
        "deployment_authorization_present": authorization is not None,
        "base_sepolia_deployed": deployed,
        "mainnet_authorized": False,
        "market_ready": False,
        "predeployment_blockers": blockers,
        "next_human_gate": (
            "Independent audit of the exact bundle, then 2-of-3 Safe addresses and "
            "a hash-bound Base Sepolia authorization."
        ),
    }
    validate_boundary("tokoin-public-readiness.schema.json", None, result)
    return result


def _ratification_short_id(ratification_id: str) -> str:
    parts = ratification_id.split("-", maxsplit=2)
    if len(parts) < 2 or parts[0] != "RAT":
        return ""
    return f"{parts[0]}-{parts[1]}"


def _load_ratified_founder_bundle() -> tuple[dict[str, Any], str] | None:
    if not RATIFIED_FOUNDER_BUNDLE_PATH.exists():
        return None
    raw = RATIFIED_FOUNDER_BUNDLE_PATH.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    bundle = json.loads(raw)
    ratifications = bundle.get("ratifications", [])
    expected = {f"RAT-{index:02d}" for index in range(1, 9)}
    observed = {_ratification_short_id(item.get("ratification_id", "")) for item in ratifications}
    if (
        bundle.get("document_type") != "FOUNDER_RATIFICATION_BUNDLE"
        or bundle.get("status")
        != "RATIFIED_PENDING_CANONICAL_INGESTION_AND_EXTERNAL_AUDIT"
        or bundle.get("effect", {}).get("human_ratification_gate") != "SATISFIED_8_OF_8"
        or len(ratifications) != 8
        or observed != expected
        or any(item.get("status") != "RATIFIED" for item in ratifications)
    ):
        raise ValueError("invalid TOKOIN founder ratification bundle")
    return bundle, digest


def deterministic_address(label: str) -> str:
    return "0x" + hashlib.sha256(f"agora-magna-tokoin:{label}".encode()).hexdigest()[:40]


def assert_allowed_chain(chain_id: int, *, require_ratification: bool = False) -> None:
    if chain_id in {1, 8453} or chain_id not in {LOCAL_CHAIN_ID, BASE_SEPOLIA_CHAIN_ID}:
        raise ValidationFailed("TOKOIN deployment is blocked for this chain_id.")
    if chain_id == BASE_SEPOLIA_CHAIN_ID and require_ratification:
        raise OwnerAuthorityRequired(
            "Base Sepolia deployment requires explicit human ratification and audit."
        )


def _decimal_string(value: int) -> str:
    return str(value)


def local_manifest_payload() -> dict[str, Any]:
    local_placeholders = {
        "token_address": deterministic_address("TokoinFixedSupply"),
        "genesis_treasury_address": deterministic_address("GenesisTreasury"),
        "reward_budget_vault_address": deterministic_address("RewardBudgetVault"),
        "challenge_escrow_address": deterministic_address("ChallengeEscrow"),
        "reward_splitter_address": deterministic_address("RewardSplitter"),
        "pool_escrow_address": deterministic_address("PoolEscrow"),
        "agent_passport_anchor_address": deterministic_address("AgentPassportAnchor"),
        "knowledge_root_registry_address": deterministic_address("KnowledgeRootRegistry"),
    }
    manifest_payload = {
        "network_key": "LOCAL_DEVNET",
        "chain_id": LOCAL_CHAIN_ID,
        "contract_suite": {"TokoinFixedSupply": local_placeholders["token_address"]},
        "local_placeholders": local_placeholders,
        "offchain_trust_boundaries": OFFCHAIN_COMPONENTS,
        "total_supply_atomic": _decimal_string(TOTAL_SUPPLY_ATOMIC),
        "decimals": TOKOIN_DECIMALS,
        "solidity_version": SOLIDITY_VERSION,
        "openzeppelin_version": OPENZEPPELIN_VERSION,
        "human_ratifications": {},
        "status": "LOCAL_SIMULATED_AUDIT_READY",
    }
    return manifest_payload


def scope_matrix_view() -> dict[str, Any]:
    """Return Sprint 04.1 scope classification without mutating live state."""
    components = [
        {
            "component": "TokoinFixedSupply",
            "classification": "IMPLEMENTED_ONCHAIN",
            "evidence": [
                "contracts/tokoin/contracts/TokoinFixedSupply.sol",
                "contracts/tokoin/scripts/static-audit.mjs",
            ],
            "release_claim": "Fixed-supply ERC-20 source, static-audited locally.",
            "blocker": None,
        },
        {
            "component": "GenesisTreasury",
            "classification": "IMPLEMENTED_OFFCHAIN_WITH_EXPLICIT_TRUST_BOUNDARY",
            "evidence": ["TokoinDeploymentManifest.genesis_treasury_address"],
            "release_claim": OFFCHAIN_COMPONENTS["GenesisTreasury"],
            "blocker": None,
        },
        {
            "component": "RewardBudgetVault",
            "classification": "IMPLEMENTED_OFFCHAIN_WITH_EXPLICIT_TRUST_BOUNDARY",
            "evidence": ["TokoinReservation", "TokoinSettlementPlan"],
            "release_claim": OFFCHAIN_COMPONENTS["RewardBudgetVault"],
            "blocker": None,
        },
        {
            "component": "ChallengeEscrow",
            "classification": "IMPLEMENTED_OFFCHAIN_WITH_EXPLICIT_TRUST_BOUNDARY",
            "evidence": ["TokoinReservation"],
            "release_claim": OFFCHAIN_COMPONENTS["ChallengeEscrow"],
            "blocker": None,
        },
        {
            "component": "RewardSplitter",
            "classification": "IMPLEMENTED_OFFCHAIN_WITH_EXPLICIT_TRUST_BOUNDARY",
            "evidence": ["ROLE_CAPS", "TokoinClaimableAllocation"],
            "release_claim": OFFCHAIN_COMPONENTS["RewardSplitter"],
            "blocker": None,
        },
        {
            "component": "PoolEscrow",
            "classification": "INTENTIONALLY_DEFERRED_AND_NOT_IN_RELEASE",
            "evidence": ["docs/work/magna-sprint-04-report.md"],
            "release_claim": OFFCHAIN_COMPONENTS["PoolEscrow"],
            "blocker": None,
        },
        {
            "component": "AgentPassportAnchor",
            "classification": "IMPLEMENTED_OFFCHAIN_WITH_EXPLICIT_TRUST_BOUNDARY",
            "evidence": ["Ed25519 Agent/Device identity", "JWS Agent Cards"],
            "release_claim": OFFCHAIN_COMPONENTS["AgentPassportAnchor"],
            "blocker": None,
        },
        {
            "component": "KnowledgeRootRegistry",
            "classification": "IMPLEMENTED_OFFCHAIN_WITH_EXPLICIT_TRUST_BOUNDARY",
            "evidence": ["TokoinKnowledgeRootAnchor", "MagnaMerkleBatch"],
            "release_claim": OFFCHAIN_COMPONENTS["KnowledgeRootRegistry"],
            "blocker": None,
        },
        {
            "component": "SettlementSaga",
            "classification": "IMPLEMENTED_OFFCHAIN_WITH_EXPLICIT_TRUST_BOUNDARY",
            "evidence": ["TokoinSettlementPlan", "processed_events"],
            "release_claim": OFFCHAIN_COMPONENTS["SettlementSaga"],
            "blocker": None,
        },
        {
            "component": "WalletBinding",
            "classification": "IMPLEMENTED_OFFCHAIN_WITH_EXPLICIT_TRUST_BOUNDARY",
            "evidence": ["TokoinWalletBinding"],
            "release_claim": OFFCHAIN_COMPONENTS["WalletBinding"],
            "blocker": None,
        },
        {
            "component": "DeploymentScriptsAndChainGuard",
            "classification": "IMPLEMENTED_OFFCHAIN_WITH_EXPLICIT_TRUST_BOUNDARY",
            "evidence": [
                "POST /v1/tokoin-testnet/deployment/guard",
                "contracts/tokoin/package.json",
            ],
            "release_claim": "Mainnet and unratified Base Sepolia deployment blocked.",
            "blocker": None,
        },
    ]
    return {
        "schema": "agora.magna.tokoin.scope_matrix.v1",
        "status": "COMPLETE_LOCAL_CLASSIFICATION",
        "components": components,
        "component_count": len(components),
        "missing_blockers": [
            item for item in components if item["classification"] == "MISSING_BLOCKER"
        ],
    }


def ratification_bundle_view() -> dict[str, Any]:
    ratified = _load_ratified_founder_bundle()
    if ratified is not None:
        source_bundle, source_hash = ratified
        attestation = source_bundle["human_attestation"]
        return {
            "schema": "agora.magna.tokoin.ratification_bundle.v1",
            "status": "COMPLETE",
            "ratifications": [
                {
                    "decision_id": _ratification_short_id(item["ratification_id"]),
                    "title": item["title"],
                    "prompt": item["ratification_id"],
                    "status": "RATIFIED",
                    "decision_value": {
                        "ratified_scope": item["ratified_scope"],
                        "founder_conditions": item["founder_conditions"],
                        "source_hash": source_hash,
                    },
                    "signed_by": source_bundle["founder"]["display_name"],
                    "signed_at": attestation["attested_at_utc"],
                    "evidence_hash": source_hash,
                }
                for item in source_bundle["ratifications"]
            ],
        }
    return {
        "schema": "agora.magna.tokoin.ratification_bundle.v1",
        "status": "PENDING_HUMAN_RATIFICATION",
        "ratifications": [
            {
                "decision_id": decision_id,
                "title": title,
                "prompt": prompt,
                "status": "PENDING",
                "decision_value": None,
                "signed_by": None,
                "signed_at": None,
                "evidence_hash": None,
            }
            for decision_id, title, prompt in RATIFICATION_DECISIONS
        ],
    }


def release_manifest_draft_view() -> dict[str, Any]:
    payload = local_manifest_payload()
    return {
        "schema": "agora.magna.tokoin.release_manifest.v1",
        "status": "DRAFT_NOT_FROZEN",
        "network_key": "LOCAL_DEVNET",
        "chain_id": LOCAL_CHAIN_ID,
        "maximum_authorized_network": "LOCAL_DEVNET",
        "deployment": manifest_preview_view(),
        "scope_matrix_hash": canonical_hash(scope_matrix_view(), domain="tokoin.scope_matrix.v1"),
        "ratification_bundle_hash": canonical_hash(
            ratification_bundle_view(), domain="tokoin.ratification_bundle.v1"
        ),
        "source_manifest_hash": canonical_hash(payload, domain="tokoin.deployment_manifest.v1"),
        "external_independent_audit_complete": False,
        "public_testnet_deployed": False,
        "mainnet_transactions": 0,
        "real_value_moved": False,
    }


async def get_local_manifest(session: AsyncSession) -> TokoinDeploymentManifest | None:
    return (
        await session.execute(
            select(TokoinDeploymentManifest).where(
                TokoinDeploymentManifest.network_key == "LOCAL_DEVNET",
                TokoinDeploymentManifest.chain_id == LOCAL_CHAIN_ID,
            )
        )
    ).scalar_one_or_none()


async def create_or_get_local_manifest(session: AsyncSession) -> TokoinDeploymentManifest:
    require_local_control_plane()
    existing = await get_local_manifest(session)
    if existing is not None:
        return existing

    manifest_payload = local_manifest_payload()
    local_placeholders = manifest_payload["local_placeholders"]
    row = TokoinDeploymentManifest(
        deployment_id=new_tokoin_deployment_id(),
        environment="LOCAL_DEVNET",
        network_key="LOCAL_DEVNET",
        chain_id=LOCAL_CHAIN_ID,
        total_supply_atomic=_decimal_string(TOTAL_SUPPLY_ATOMIC),
        decimals=TOKOIN_DECIMALS,
        solidity_version=SOLIDITY_VERSION,
        openzeppelin_version=OPENZEPPELIN_VERSION,
        manifest_hash=canonical_hash(manifest_payload, domain="tokoin.deployment_manifest.v1"),
        status="LOCAL_SIMULATED_AUDIT_READY",
        source_verified=True,
        bytecode_verified=False,
        human_ratifications={},
        created_at=now_utc(),
        **local_placeholders,
    )
    session.add(row)
    await append_event(
        session,
        event_type="tokoin.deployment.manifest_created",
        actor={"agent_id": SYSTEM_ACTOR_ID},
        payload={
            "deployment_id": row.deployment_id,
            "network_key": row.network_key,
            "chain_id": row.chain_id,
            "manifest_hash": row.manifest_hash,
            "real_value_moved": False,
            "public_testnet_deployed": False,
        },
    )
    return row


def manifest_view(row: TokoinDeploymentManifest) -> dict[str, Any]:
    return {
        "deployment_id": row.deployment_id,
        "network_key": row.network_key,
        "chain_id": row.chain_id,
        "status": row.status,
        "classification": "LOCAL_DEVNET_TEST_ONLY_NO_ECONOMIC_VALUE",
        "contracts": {
            "TokoinFixedSupply": row.token_address,
        },
        "contract_suite": {
            "TokoinFixedSupply": {
                "source": "contracts/tokoin/contracts/TokoinFixedSupply.sol",
                "address": row.token_address,
                "deployment_state": "LOCAL_DEVNET_PLACEHOLDER_NOT_PUBLIC_TESTNET",
                "upgradeability": False,
                "mintability_after_genesis": False,
            }
        },
        "offchain_trust_boundaries": OFFCHAIN_COMPONENTS,
        "local_placeholder_addresses": {
            "GenesisTreasury": row.genesis_treasury_address,
            "RewardBudgetVault": row.reward_budget_vault_address,
            "ChallengeEscrow": row.challenge_escrow_address,
            "RewardSplitter": row.reward_splitter_address,
            "PoolEscrow": row.pool_escrow_address,
            "AgentPassportAnchor": row.agent_passport_anchor_address,
            "KnowledgeRootRegistry": row.knowledge_root_registry_address,
        },
        "total_supply_atomic": row.total_supply_atomic,
        "decimals": row.decimals,
        "solidity_version": row.solidity_version,
        "openzeppelin_version": row.openzeppelin_version,
        "manifest_hash": row.manifest_hash,
        "source_verified": row.source_verified,
        "bytecode_verified": row.bytecode_verified,
        "human_ratifications": row.human_ratifications,
        "mainnet_transactions": 0,
        "real_value_moved": False,
    }


def manifest_preview_view() -> dict[str, Any]:
    payload = local_manifest_payload()
    local_placeholders = payload["local_placeholders"]
    return {
        "deployment_id": None,
        "network_key": payload["network_key"],
        "chain_id": payload["chain_id"],
        "status": "LOCAL_SIMULATED_NOT_PERSISTED",
        "classification": "LOCAL_DEVNET_TEST_ONLY_NO_ECONOMIC_VALUE",
        "contracts": {
            "TokoinFixedSupply": local_placeholders["token_address"],
        },
        "contract_suite": {
            "TokoinFixedSupply": {
                "source": "contracts/tokoin/contracts/TokoinFixedSupply.sol",
                "address": local_placeholders["token_address"],
                "deployment_state": "LOCAL_DEVNET_PLACEHOLDER_NOT_PUBLIC_TESTNET",
                "upgradeability": False,
                "mintability_after_genesis": False,
            }
        },
        "offchain_trust_boundaries": OFFCHAIN_COMPONENTS,
        "local_placeholder_addresses": {
            "GenesisTreasury": local_placeholders["genesis_treasury_address"],
            "RewardBudgetVault": local_placeholders["reward_budget_vault_address"],
            "ChallengeEscrow": local_placeholders["challenge_escrow_address"],
            "RewardSplitter": local_placeholders["reward_splitter_address"],
            "PoolEscrow": local_placeholders["pool_escrow_address"],
            "AgentPassportAnchor": local_placeholders["agent_passport_anchor_address"],
            "KnowledgeRootRegistry": local_placeholders["knowledge_root_registry_address"],
        },
        "total_supply_atomic": payload["total_supply_atomic"],
        "decimals": payload["decimals"],
        "solidity_version": payload["solidity_version"],
        "openzeppelin_version": payload["openzeppelin_version"],
        "manifest_hash": canonical_hash(payload, domain="tokoin.deployment_manifest.v1"),
        "source_verified": True,
        "bytecode_verified": False,
        "human_ratifications": {},
        "mainnet_transactions": 0,
        "real_value_moved": False,
    }


async def bind_wallet(
    session: AsyncSession, *, actor: Agent, payload: dict[str, Any]
) -> TokoinWalletBinding:
    validate_boundary("tokoins.schema.json", "/$defs/WalletBindingRequest", payload)
    if payload["agent_id"] != actor.agent_id:
        raise OwnerAuthorityRequired("An Agent cannot bind a wallet for another Agent.")
    existing = (
        await session.execute(
            select(TokoinWalletBinding).where(
                TokoinWalletBinding.agent_id == actor.agent_id,
                TokoinWalletBinding.chain_id == LOCAL_CHAIN_ID,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    ts = now_utc()
    row = TokoinWalletBinding(
        binding_id=new_tokoin_wallet_binding_id(),
        agent_id=actor.agent_id,
        controller_commitment_hash=payload["controller_commitment_hash"],
        wallet_address=payload["wallet_address"],
        state="TESTNET_RECEIVE_ONLY",
        chain_id=LOCAL_CHAIN_ID,
        balance_cache_atomic="0",
        session_policy=payload.get("session_policy") or {
            "default": "receive_only",
            "llm_signing_authority": False,
            "private_key_material_stored": False,
        },
        created_at=ts,
        updated_at=ts,
    )
    session.add(row)
    await append_event(
        session,
        event_type="tokoin.wallet.bound",
        actor={"agent_id": actor.agent_id, "agent_version_id": actor.current_version_id},
        payload={
            "binding_id": row.binding_id,
            "chain_id": LOCAL_CHAIN_ID,
            "state": row.state,
            "balance_cache_authoritative": False,
        },
    )
    return row


def wallet_binding_view(row: TokoinWalletBinding) -> dict[str, Any]:
    return {
        "binding_id": row.binding_id,
        "agent_id": row.agent_id,
        "wallet_address": row.wallet_address,
        "controller_commitment_hash": row.controller_commitment_hash,
        "state": row.state,
        "chain_id": row.chain_id,
        "balance_cache_atomic": row.balance_cache_atomic,
        "balance_cache_authoritative": False,
        "session_policy": row.session_policy,
        "created_at": row.created_at.isoformat().replace("+00:00", "Z"),
    }


async def request_reservation(
    session: AsyncSession, payload: dict[str, Any], *, owner_id: str
) -> TokoinReservation:
    require_local_control_plane()
    validate_boundary("tokoins.schema.json", "/$defs/ReservationRequest", payload)
    manifest = await create_or_get_local_manifest(session)
    existing = (
        await session.execute(
            select(TokoinReservation).where(
                TokoinReservation.idempotency_key == payload["idempotency_key"]
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        _require_reservation_operator(existing, owner_id)
        return existing
    by_challenge = (
        await session.execute(
            select(TokoinReservation).where(
                TokoinReservation.world_instance_id == payload["world_instance_id"],
                TokoinReservation.challenge_id == payload["challenge_id"],
            )
        )
    ).scalar_one_or_none()
    if by_challenge is not None:
        raise Conflict("Challenge already has an immutable TOKOIN reservation.")
    ts = now_utc()
    row = TokoinReservation(
        reservation_id=new_research_reservation_id(),
        idempotency_key=payload["idempotency_key"],
        world_instance_id=payload["world_instance_id"],
        challenge_id=payload["challenge_id"],
        candidate_id=payload["candidate_id"],
        requested_by_owner_id=owner_id,
        settlement_backend=SETTLEMENT_BACKEND,
        chain_id=LOCAL_CHAIN_ID,
        escrow_address=manifest.challenge_escrow_address,
        state="RESERVATION_REQUESTED",
        amount_atomic=_decimal_string(ONE_TOKOIN_ATOMIC),
        created_at=ts,
        updated_at=ts,
    )
    session.add(row)
    await append_event(
        session,
        event_type="tokoin.reservation.requested",
        actor={"agent_id": SYSTEM_ACTOR_ID},
        payload={
            "reservation_id": row.reservation_id,
            "challenge_id": row.challenge_id,
            "backend": row.settlement_backend,
            "amount_atomic": row.amount_atomic,
            "real_value_moved": False,
        },
    )
    return row


async def confirm_local_reservation(
    session: AsyncSession, reservation_id: str, *, owner_id: str
) -> TokoinReservation:
    require_local_control_plane()
    row = await session.get(TokoinReservation, reservation_id)
    if row is None:
        raise NotFound("TOKOIN reservation not found.")
    _require_reservation_operator(row, owner_id)
    if row.state in {"RESERVED", "RELEASED_ACTIVE"}:
        return row
    if row.state not in {"RESERVATION_REQUESTED", "ONCHAIN_PENDING", "FINALITY_CONFIRMED"}:
        raise Conflict("Reservation cannot be confirmed from its current state.")
    ts = now_utc()
    tx_hash = "0x" + canonical_hash(
        {"reservation_id": row.reservation_id, "state": "local_reserved"},
        domain="tokoin.local_tx.v1",
    )
    row.state = "RESERVED"
    row.tx_hash = tx_hash
    row.finality_evidence = {
        "mode": "local_devnet_simulated",
        "chain_id": LOCAL_CHAIN_ID,
        "confirmations": 1,
        "irreversible_finality_claimed": False,
    }
    row.updated_at = ts
    await append_event(
        session,
        event_type="tokoin.reservation.reserved",
        actor={"agent_id": SYSTEM_ACTOR_ID},
        payload={
            "reservation_id": row.reservation_id,
            "challenge_id": row.challenge_id,
            "tx_hash": tx_hash,
            "finality_policy": row.finality_evidence,
        },
    )
    return row


def reservation_view(row: TokoinReservation) -> dict[str, Any]:
    return {
        "reservation_id": row.reservation_id,
        "world_instance_id": row.world_instance_id,
        "challenge_id": row.challenge_id,
        "candidate_id": row.candidate_id,
        "settlement_backend": row.settlement_backend,
        "chain_id": row.chain_id,
        "escrow_address": row.escrow_address,
        "state": row.state,
        "amount_atomic": row.amount_atomic,
        "tx_hash": row.tx_hash,
        "finality_evidence": row.finality_evidence,
        "resolution_receipt_id": row.resolution_receipt_id,
        "settlement_plan_hash": row.settlement_plan_hash,
        "created_at": row.created_at.isoformat().replace("+00:00", "Z"),
    }


def _validate_allocations(allocations: list[dict[str, Any]]) -> tuple[int, int]:
    totals_by_role = {role: 0 for role in ROLE_CAPS}
    for allocation in allocations:
        amount = int(allocation["amount_atomic"])
        role = allocation["role"]
        totals_by_role[role] += amount
        if totals_by_role[role] > ROLE_CAPS[role]:
            raise ValidationFailed(f"TOKOIN settlement exceeds cap for role {role}.")
    total = sum(totals_by_role.values())
    if total > ONE_TOKOIN_ATOMIC:
        raise ValidationFailed("TOKOIN settlement exceeds one TOKOIN.")
    return total, ONE_TOKOIN_ATOMIC - total


async def create_settlement_plan(
    session: AsyncSession, payload: dict[str, Any], *, owner_id: str
) -> TokoinSettlementPlan:
    require_local_control_plane()
    validate_boundary("tokoins.schema.json", "/$defs/SettlementPlanRequest", payload)
    reservation = await session.get(TokoinReservation, payload["reservation_id"])
    if reservation is None:
        raise NotFound("TOKOIN reservation not found.")
    _require_reservation_operator(reservation, owner_id)
    receipt = await session.get(MagnaResolutionReceipt, payload["resolution_receipt_id"])
    if receipt is None:
        raise NotFound("ResolutionReceipt not found.")
    if receipt.challenge_id != reservation.challenge_id:
        raise ValidationFailed("ResolutionReceipt is not bound to this challenge.")
    if receipt.decision != "accepted" or receipt.requested_state != "RESOLVED_VERIFIED":
        raise ValidationFailed("Settlement requires an accepted RESOLVED_VERIFIED receipt.")
    existing = (
        await session.execute(
            select(TokoinSettlementPlan).where(
                TokoinSettlementPlan.challenge_id == reservation.challenge_id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    if reservation.state != "RESERVED":
        raise Conflict("Settlement requires a RESERVED TOKOIN reservation.")

    total, unused = _validate_allocations(payload["allocations"])
    restricted = {"independent_replication", "review_and_adjudication"}
    controller_by_restricted_role: dict[str, set[str]] = {}
    for allocation in payload["allocations"]:
        if allocation["role"] in restricted:
            controller_by_restricted_role.setdefault(allocation["role"], set()).add(
                allocation["controller_commitment_hash"]
            )
    shared_controllers = set.intersection(*controller_by_restricted_role.values()) if len(
        controller_by_restricted_role
    ) > 1 else set()
    if shared_controllers:
        raise ValidationFailed("Same controller cannot unlock independent replication and review.")

    plan_payload = {
        "challenge_id": reservation.challenge_id,
        "reservation_id": reservation.reservation_id,
        "resolution_receipt_id": receipt.receipt_id,
        "allocations": payload["allocations"],
        "unused_return_atomic": str(unused),
    }
    plan_hash = canonical_hash(plan_payload, domain="tokoin.settlement_plan.v1")
    ts = now_utc()
    plan = TokoinSettlementPlan(
        settlement_plan_id=new_tokoin_settlement_plan_id(),
        challenge_id=reservation.challenge_id,
        reservation_id=reservation.reservation_id,
        resolution_receipt_id=receipt.receipt_id,
        plan_hash=plan_hash,
        state="ALLOCATED",
        total_atomic=str(ONE_TOKOIN_ATOMIC),
        role_allocations=payload["allocations"],
        unused_return_atomic=str(unused),
        created_at=ts,
        settled_at=ts,
    )
    session.add(plan)
    await session.flush()
    for allocation in payload["allocations"]:
        binding = await session.get(TokoinWalletBinding, allocation["wallet_binding_id"])
        if binding is None or binding.agent_id != allocation["agent_id"]:
            raise ValidationFailed("Allocation wallet binding does not match Agent.")
        session.add(
            TokoinClaimableAllocation(
                allocation_id=new_tokoin_claimable_allocation_id(),
                settlement_plan_id=plan.settlement_plan_id,
                agent_id=allocation["agent_id"],
                wallet_binding_id=allocation["wallet_binding_id"],
                role=allocation["role"],
                amount_atomic=allocation["amount_atomic"],
                controller_commitment_hash=allocation["controller_commitment_hash"],
                state="CLAIMABLE",
                created_at=ts,
            )
        )
    reservation.resolution_receipt_id = receipt.receipt_id
    reservation.settlement_plan_hash = plan_hash
    reservation.state = "RELEASED_ACTIVE"
    reservation.updated_at = ts
    await append_event(
        session,
        event_type="tokoin.settlement.allocated",
        actor={"agent_id": SYSTEM_ACTOR_ID},
        payload={
            "settlement_plan_id": plan.settlement_plan_id,
            "challenge_id": plan.challenge_id,
            "plan_hash": plan.plan_hash,
            "total_allocated_atomic": str(total),
            "unused_return_atomic": plan.unused_return_atomic,
            "real_value_moved": False,
        },
    )
    return plan


def settlement_plan_view(row: TokoinSettlementPlan) -> dict[str, Any]:
    return {
        "settlement_plan_id": row.settlement_plan_id,
        "challenge_id": row.challenge_id,
        "reservation_id": row.reservation_id,
        "resolution_receipt_id": row.resolution_receipt_id,
        "plan_hash": row.plan_hash,
        "state": row.state,
        "total_atomic": row.total_atomic,
        "role_allocations": row.role_allocations,
        "unused_return_atomic": row.unused_return_atomic,
        "pull_withdrawals_only": True,
        "real_value_moved": False,
    }


async def anchor_knowledge_root(
    session: AsyncSession, payload: dict[str, Any]
) -> TokoinKnowledgeRootAnchor:
    require_local_control_plane()
    validate_boundary("tokoins.schema.json", "/$defs/KnowledgeRootAnchorRequest", payload)
    batch = await session.get(MagnaMerkleBatch, payload["merkle_batch_id"])
    if batch is None:
        raise NotFound("MerkleBatch not found.")
    existing = (
        await session.execute(
            select(TokoinKnowledgeRootAnchor).where(
                TokoinKnowledgeRootAnchor.merkle_batch_id == batch.batch_id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    previous = (
        await session.execute(
            select(TokoinKnowledgeRootAnchor)
            .where(TokoinKnowledgeRootAnchor.world_instance_id == batch.world_instance_id)
            .order_by(TokoinKnowledgeRootAnchor.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    row = TokoinKnowledgeRootAnchor(
        anchor_id=new_tokoin_knowledge_root_anchor_id(),
        merkle_batch_id=batch.batch_id,
        world_instance_id=batch.world_instance_id,
        merkle_root=batch.merkle_root,
        previous_root_hash=previous.merkle_root if previous else None,
        chain_id=LOCAL_CHAIN_ID,
        state="LOCAL_ANCHORED",
        created_at=now_utc(),
    )
    session.add(row)
    await append_event(
        session,
        event_type="tokoin.knowledge_root.anchored",
        actor={"agent_id": SYSTEM_ACTOR_ID},
        payload={
            "anchor_id": row.anchor_id,
            "merkle_batch_id": row.merkle_batch_id,
            "merkle_root": row.merkle_root,
            "chain_id": row.chain_id,
            "plaintext_included": False,
        },
    )
    return row


def knowledge_root_view(row: TokoinKnowledgeRootAnchor) -> dict[str, Any]:
    return {
        "anchor_id": row.anchor_id,
        "merkle_batch_id": row.merkle_batch_id,
        "world_instance_id": row.world_instance_id,
        "merkle_root": row.merkle_root,
        "previous_root_hash": row.previous_root_hash,
        "chain_id": row.chain_id,
        "state": row.state,
        "tx_hash": row.tx_hash,
    }
