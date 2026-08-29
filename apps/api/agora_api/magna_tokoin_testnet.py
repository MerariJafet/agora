"""MAGNA Sprint 04 TOKOIN local-devnet control plane.

This module models the audit-ready TOKOIN testnet integration without creating
keys, touching mainnet, converting legacy balances, or pretending local state is
authoritative on-chain balance. Public testnet deployment is gated by human
ratification and independent audit.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.boundary import validate_boundary
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
ROLE_CAPS = {
    "proposer": 1_000_000,
    "contributors": 59_000_000,
    "independent_replication": 25_000_000,
    "review_and_adjudication": 10_000_000,
    "data_tools_infrastructure": 5_000_000,
}


def canonical_hash(payload: dict[str, Any], *, domain: str) -> str:
    raw = json.dumps(
        {"domain": domain, "payload": payload}, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(raw).hexdigest()


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
    contracts = {
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
        "contracts": contracts,
        "total_supply_atomic": _decimal_string(TOTAL_SUPPLY_ATOMIC),
        "decimals": TOKOIN_DECIMALS,
        "solidity_version": SOLIDITY_VERSION,
        "openzeppelin_version": OPENZEPPELIN_VERSION,
        "human_ratifications": {},
        "status": "LOCAL_SIMULATED_AUDIT_READY",
    }
    return manifest_payload


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
    existing = await get_local_manifest(session)
    if existing is not None:
        return existing

    manifest_payload = local_manifest_payload()
    contracts = manifest_payload["contracts"]
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
        **contracts,
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
    contracts = payload["contracts"]
    return {
        "deployment_id": None,
        "network_key": payload["network_key"],
        "chain_id": payload["chain_id"],
        "status": "LOCAL_SIMULATED_NOT_PERSISTED",
        "classification": "LOCAL_DEVNET_TEST_ONLY_NO_ECONOMIC_VALUE",
        "contracts": {
            "TokoinFixedSupply": contracts["token_address"],
            "GenesisTreasury": contracts["genesis_treasury_address"],
            "RewardBudgetVault": contracts["reward_budget_vault_address"],
            "ChallengeEscrow": contracts["challenge_escrow_address"],
            "RewardSplitter": contracts["reward_splitter_address"],
            "PoolEscrow": contracts["pool_escrow_address"],
            "AgentPassportAnchor": contracts["agent_passport_anchor_address"],
            "KnowledgeRootRegistry": contracts["knowledge_root_registry_address"],
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


async def request_reservation(session: AsyncSession, payload: dict[str, Any]) -> TokoinReservation:
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
    session: AsyncSession, reservation_id: str
) -> TokoinReservation:
    row = await session.get(TokoinReservation, reservation_id)
    if row is None:
        raise NotFound("TOKOIN reservation not found.")
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
    session: AsyncSession, payload: dict[str, Any]
) -> TokoinSettlementPlan:
    validate_boundary("tokoins.schema.json", "/$defs/SettlementPlanRequest", payload)
    reservation = await session.get(TokoinReservation, payload["reservation_id"])
    if reservation is None:
        raise NotFound("TOKOIN reservation not found.")
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
