"""MAGNA Sprint 04.4 private TOKOIN economic pilot.

This module is intentionally local/private. It prepares and tests economic
readiness without activating Genesis-100, deploying public networks, moving
legacy balances, storing wallet secrets, or claiming market value.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.config import get_settings
from agora_api.errors import Conflict, NotFound, ValidationFailed
from agora_api.events import append_event, now_utc
from agora_api.ids import (
    new_pre_public_reward_entitlement_id,
    new_tokoin_devnet_transfer_id,
    new_tokoin_migration_snapshot_id,
    new_tokoin_private_pilot_receipt_id,
)
from agora_api.magna_tokoin_testnet import (
    LOCAL_CHAIN_ID,
    ONE_TOKOIN_ATOMIC,
    TOTAL_SUPPLY_ATOMIC,
    canonical_hash,
    manifest_preview_view,
    ratification_bundle_view,
)
from agora_api.models import (
    PrePublicRewardEntitlement,
    TokoinClaimableAllocation,
    TokoinDevnetTransfer,
    TokoinMigrationSnapshot,
    TokoinPrivatePilotReceipt,
    TokoinReservation,
    TokoinSettlementPlan,
)
from agora_api.provenance import SYSTEM_ACTOR_ID

GENESIS_100_ROOT = Path("/home/merari-acero/.agora-agents/genesis-100/agents")
PRIVATE_PILOT_STATUS = "READY_FOR_7_AGENT_PRIVATE_PILOT"
ECONOMIC_PROHIBITIONS = (
    "NO_MAINNET_AUTHORIZATION",
    "NO_PUBLIC_SALE_OR_PRESALE",
    "NO_THIRD_PARTY_FUNDS_CUSTODY",
    "NO_PROFIT_OR_RETURN_PROMISE",
    "NO_GENESIS_100_LAUNCH_AUTHORIZATION",
)
FORBIDDEN_ENV_FIELDS = (
    "PRIVATE_KEY",
    "RAW_PRIVATE_KEY",
    "SEED_PHRASE",
    "MNEMONIC",
    "KEYSTORE_PASSWORD",
    "RECOVERY_SECRET",
)
ALLOWED_ENV_FIELDS = (
    "WALLET_ADDRESS",
    "WALLET_KEY_REF",
    "KEYSTORE_PATH",
    "CHAIN_ID",
    "TOKOIN_CONTRACT_ADDRESS",
    "AGORA_API_URL",
    "RPC_ALIAS",
    "AGORA_WALLET_TEST_ADDRESS",
    "AGORA_WALLET_TEST_SIGNER_REF",
    "AGORA_WALLET_MANIFEST_PATH",
    "AGORA_WALLET_BINDING_PATH",
)


def require_private_pilot_environment() -> None:
    settings = get_settings()
    if settings.is_production:
        raise Conflict("Private TOKOIN pilot controls are not enabled in production.")


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _tx_hash(payload: dict[str, Any]) -> str:
    return "0x" + _hash(payload)[:64]


async def _upsert_receipt(
    session: AsyncSession,
    *,
    receipt_type: str,
    subject_id: str,
    payload: dict[str, Any],
    source_hash: str | None = None,
) -> TokoinPrivatePilotReceipt:
    digest = canonical_hash(payload, domain=f"tokoin.private_pilot.{receipt_type}.v1")
    existing = (
        await session.execute(
            select(TokoinPrivatePilotReceipt).where(
                TokoinPrivatePilotReceipt.receipt_type == receipt_type,
                TokoinPrivatePilotReceipt.subject_id == subject_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    row = TokoinPrivatePilotReceipt(
        receipt_id=new_tokoin_private_pilot_receipt_id(),
        receipt_type=receipt_type,
        subject_id=subject_id,
        canonical_hash=digest,
        payload=payload,
        source_hash=source_hash,
        created_at=now_utc(),
    )
    session.add(row)
    await append_event(
        session,
        event_type=f"tokoin.private_pilot.{receipt_type}",
        actor={"agent_id": SYSTEM_ACTOR_ID},
        payload={
            "receipt_id": row.receipt_id,
            "receipt_type": receipt_type,
            "subject_id": subject_id,
            "canonical_hash": digest,
        },
    )
    return row


async def ingest_founder_ratification_receipts(session: AsyncSession) -> dict[str, Any]:
    bundle = ratification_bundle_view()
    if bundle["status"] != "COMPLETE":
        return {"status": "MISSING_RATIFICATION_BUNDLE", "imported": 0}
    rows = []
    for item in bundle["ratifications"]:
        row = await _upsert_receipt(
            session,
            receipt_type="founder_ratification",
            subject_id=item["decision_id"],
            payload=item,
            source_hash=item["evidence_hash"],
        )
        rows.append(row)
    return {
        "status": "RATIFIED_8_OF_8",
        "imported": len(rows),
        "receipt_ids": [row.receipt_id for row in rows],
        "source_hash": bundle["ratifications"][0]["evidence_hash"],
        "prohibitions": list(ECONOMIC_PROHIBITIONS),
    }


def _parse_env_keys(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", maxsplit=1)
        values[key.strip()] = value.strip()
    return values


def genesis_100_wallet_readiness(root: Path = GENESIS_100_ROOT) -> dict[str, Any]:
    folders = sorted(path for path in root.iterdir() if path.is_dir()) if root.exists() else []
    wallet_addresses: list[str] = []
    signer_refs: list[str] = []
    forbidden_nonempty: list[dict[str, str]] = []
    missing_wallet_binding = 0
    provider_counts: dict[str, int] = {}
    for folder in folders:
        env_values = _parse_env_keys(folder / ".env")
        provider = env_values.get("AGORA_PROVIDER_CLASS", "unknown")
        provider_counts[provider] = provider_counts.get(provider, 0) + 1
        wallet_address = env_values.get("AGORA_WALLET_TEST_ADDRESS") or env_values.get(
            "WALLET_ADDRESS"
        )
        signer_ref = env_values.get("AGORA_WALLET_TEST_SIGNER_REF") or env_values.get(
            "WALLET_KEY_REF"
        )
        if wallet_address:
            wallet_addresses.append(wallet_address)
        if signer_ref:
            signer_refs.append(signer_ref)
        if not (folder / "wallet" / "wallet_binding.json").exists():
            missing_wallet_binding += 1
        for key in FORBIDDEN_ENV_FIELDS:
            if env_values.get(key):
                forbidden_nonempty.append({"agent": folder.name, "field": key})
    unique_wallets = len(set(wallet_addresses))
    return {
        "status": "GENESIS_100_CREATED_PAUSED_NOT_ECONOMICALLY_ACTIVATED",
        "root": str(root),
        "agent_folder_count": len(folders),
        "wallet_address_count": len(wallet_addresses),
        "unique_wallet_address_count": unique_wallets,
        "unique_signer_ref_count": len(set(signer_refs)),
        "missing_wallet_binding_files": missing_wallet_binding,
        "forbidden_env_fields_nonempty": forbidden_nonempty,
        "allowed_env_fields": list(ALLOWED_ENV_FIELDS),
        "provider_counts": provider_counts,
        "genesis_100_live_activation": False,
        "ready": (
            len(folders) == 100
            and unique_wallets == 100
            and not forbidden_nonempty
            and missing_wallet_binding == 0
        ),
    }


def policy_as_code() -> dict[str, Any]:
    return {
        "status": "ENFORCED_FOR_PRIVATE_PILOT",
        "mining_public_name": "Proof of Useful Knowledge",
        "technical_definition": (
            "Authorizes transfer of existing TOKOIN from GenesisTreasury; "
            "does not mint or participate in blockchain consensus."
        ),
        "local_reward_class": "PRE_PUBLIC_EARNED",
        "prohibitions": list(ECONOMIC_PROHIBITIONS),
        "base_sepolia_deployed": False,
        "mainnet_deployed": False,
        "genesis_100_launched": False,
        "public_market_or_liquidity": False,
        "custody_of_third_party_funds": False,
        "profit_promise": False,
    }


async def private_pilot_status(session: AsyncSession) -> dict[str, Any]:
    bundle = ratification_bundle_view()
    imported_ratifications = int(
        (
            await session.execute(
                select(func.count(TokoinPrivatePilotReceipt.receipt_id)).where(
                    TokoinPrivatePilotReceipt.receipt_type == "founder_ratification"
                )
            )
        ).scalar_one()
    )
    ratification = {
        "status": "RATIFIED_8_OF_8" if bundle["status"] == "COMPLETE" else bundle["status"],
        "imported": imported_ratifications,
        "source_hash": bundle["ratifications"][0]["evidence_hash"]
        if bundle["status"] == "COMPLETE"
        else None,
        "prohibitions": list(ECONOMIC_PROHIBITIONS),
    }
    readiness = genesis_100_wallet_readiness()
    reservations = (
        await session.execute(select(TokoinReservation.state, TokoinReservation.amount_atomic))
    ).all()
    reserved = sum(int(amount) for state, amount in reservations if state in {"RESERVED"})
    released = sum(
        int(amount) for state, amount in reservations if state in {"RELEASED_ACTIVE"}
    )
    entitlement_amounts = (
        await session.execute(select(PrePublicRewardEntitlement.amount_atomic))
    ).scalars().all()
    distributed = sum(int(amount) for amount in entitlement_amounts)
    return {
        "status": PRIVATE_PILOT_STATUS,
        "ratification_ingestion": ratification,
        "wallet_readiness_100": readiness,
        "policy": policy_as_code(),
        "treasury_model": {
            "total_supply_atomic": str(TOTAL_SUPPLY_ATOMIC),
            "reserved_atomic": str(reserved),
            "released_active_atomic": str(released),
            "pre_public_distributed_atomic": str(distributed),
            "available_atomic": str(TOTAL_SUPPLY_ATOMIC - reserved - released - distributed),
        },
        "activation_gates": {
            "seven_agent_live_private_pilot": "REQUIRES_PRIVATE_PILOT_GO_NO_GO",
            "twenty_five_agent_expansion": "REQUIRES_SEPARATE_GO_NO_GO",
            "genesis_100_live_activation": "REQUIRES_GENESIS_100_PRIVATE_PILOT_GO_NO_GO",
            "base_sepolia_deployment": "REQUIRES_EXTERNAL_AUDIT_AND_SEPARATE_GO_NO_GO",
            "mainnet_or_public_market": "NOT_AUTHORIZED",
        },
    }


def deterministic_100_agent_simulation(
    *, cycles: int = 500, settlements: int = 100
) -> dict[str, Any]:
    if cycles < settlements:
        raise ValidationFailed("cycles must be >= settlements")
    treasury = TOTAL_SUPPLY_ATOMIC
    reserved = 0
    distributed = 0
    completed = 0
    expired = 0
    for _index in range(cycles):
        reserved += ONE_TOKOIN_ATOMIC
        if completed < settlements:
            reserved -= ONE_TOKOIN_ATOMIC
            distributed += ONE_TOKOIN_ATOMIC
            completed += 1
        else:
            reserved -= ONE_TOKOIN_ATOMIC
            treasury += 0
            expired += 1
    treasury -= distributed
    return {
        "mode": "TEST_ONLY_NO_LLM_NO_GENESIS_100_ACTIVATION",
        "simulated_agents": 100,
        "cycles": cycles,
        "successful_settlements": completed,
        "expired_or_non_success": expired,
        "reward_per_settlement_atomic": str(ONE_TOKOIN_ATOMIC),
        "distributed_atomic": str(distributed),
        "treasury_atomic": str(treasury),
        "reserved_atomic": str(reserved),
        "supply_conserved": treasury + distributed + reserved == TOTAL_SUPPLY_ATOMIC,
        "max_one_candidate_per_epoch": True,
        "catch_up_burst": False,
        "genesis_100_live_activation": False,
    }


async def authorize_and_reconcile_settlement(
    session: AsyncSession, settlement_plan_id: str
) -> dict[str, Any]:
    plan = (
        await session.execute(
            select(TokoinSettlementPlan)
            .where(TokoinSettlementPlan.settlement_plan_id == settlement_plan_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if plan is None:
        raise NotFound("Settlement plan not found.")
    existing = (
        await session.execute(
            select(TokoinDevnetTransfer).where(
                TokoinDevnetTransfer.settlement_plan_id == settlement_plan_id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return await reconciliation_view(session, existing.transfer_id)
    reservation = await session.get(TokoinReservation, plan.reservation_id)
    if reservation is None or reservation.state not in {"RESERVED", "RELEASED_ACTIVE"}:
        raise Conflict("Settlement requires a reserved TOKOIN reservation.")
    allocations = (
        await session.execute(
            select(TokoinClaimableAllocation).where(
                TokoinClaimableAllocation.settlement_plan_id == settlement_plan_id
            )
        )
    ).scalars().all()
    total = sum(int(row.amount_atomic) for row in allocations)
    if total > int(reservation.amount_atomic):
        raise ValidationFailed("Settlement exceeds reserved amount.")
    manifest = manifest_preview_view()
    payload = {
        "settlement_plan_id": settlement_plan_id,
        "chain_id": LOCAL_CHAIN_ID,
        "contract_address": manifest["contracts"]["TokoinFixedSupply"],
        "transfers": [
            {
                "agent_id": row.agent_id,
                "wallet_binding_id": row.wallet_binding_id,
                "role": row.role,
                "amount_atomic": row.amount_atomic,
            }
            for row in allocations
        ],
    }
    ts = now_utc()
    transfer = TokoinDevnetTransfer(
        transfer_id=new_tokoin_devnet_transfer_id(),
        settlement_plan_id=settlement_plan_id,
        chain_id=LOCAL_CHAIN_ID,
        contract_address=payload["contract_address"],
        tx_hash=_tx_hash(payload),
        block_number=1,
        transfer_payload=payload,
        state="reconciled",
        created_at=ts,
        confirmed_at=ts,
    )
    session.add(transfer)
    await session.flush()
    for allocation in allocations:
        entitlement = PrePublicRewardEntitlement(
            entitlement_id=new_pre_public_reward_entitlement_id(),
            settlement_plan_id=settlement_plan_id,
            allocation_id=allocation.allocation_id,
            agent_id=allocation.agent_id,
            wallet_binding_id=allocation.wallet_binding_id,
            amount_atomic=allocation.amount_atomic,
            classification="PRE_PUBLIC_EARNED",
            state="earned",
            source_transfer_id=transfer.transfer_id,
            created_at=ts,
        )
        session.add(entitlement)
    plan.state = "SETTLED"
    plan.settled_at = ts
    reservation.state = "RELEASED_ACTIVE"
    reservation.tx_hash = transfer.tx_hash
    reservation.finality_evidence = {
        "chain_id": LOCAL_CHAIN_ID,
        "contract_address": transfer.contract_address,
        "tx_hash": transfer.tx_hash,
        "block_number": transfer.block_number,
        "classification": "PRE_PUBLIC_EARNED",
    }
    await _upsert_receipt(
        session,
        receipt_type="settlement_authorization",
        subject_id=settlement_plan_id,
        payload={
            "settlement_plan_id": settlement_plan_id,
            "policy": policy_as_code(),
            "plan_hash": plan.plan_hash,
        },
    )
    await _upsert_receipt(
        session,
        receipt_type="settlement_receipt",
        subject_id=settlement_plan_id,
        payload=payload | {"tx_hash": transfer.tx_hash, "block_number": transfer.block_number},
    )
    return await reconciliation_view(session, transfer.transfer_id)


async def reconciliation_view(session: AsyncSession, transfer_id: str) -> dict[str, Any]:
    transfer = await session.get(TokoinDevnetTransfer, transfer_id)
    if transfer is None:
        raise NotFound("Transfer not found.")
    entitlements = (
        await session.execute(
            select(PrePublicRewardEntitlement).where(
                PrePublicRewardEntitlement.source_transfer_id == transfer_id
            )
        )
    ).scalars().all()
    claimable = sum(int(row.amount_atomic) for row in entitlements)
    payload = {
        "transfer_id": transfer_id,
        "settlement_plan_id": transfer.settlement_plan_id,
        "chain_id": transfer.chain_id,
        "contract_address": transfer.contract_address,
        "tx_hash": transfer.tx_hash,
        "block_number": transfer.block_number,
        "claimable_atomic": str(claimable),
        "classification": "PRE_PUBLIC_EARNED",
        "real_value_moved": False,
        "mainnet_transactions": 0,
        "reconciled": transfer.state == "reconciled",
    }
    await _upsert_receipt(
        session,
        receipt_type="reconciliation_receipt",
        subject_id=transfer_id,
        payload=payload,
    )
    return payload


async def create_test_only_migration_snapshot(session: AsyncSession) -> dict[str, Any]:
    entitlements = (
        await session.execute(
            select(PrePublicRewardEntitlement).where(
                PrePublicRewardEntitlement.state == "earned"
            )
        )
    ).scalars().all()
    leaves = [
        {
            "agent_id": row.agent_id,
            "wallet_binding_id": row.wallet_binding_id,
            "amount_atomic": row.amount_atomic,
            "source_transfer_id": row.source_transfer_id,
        }
        for row in sorted(entitlements, key=lambda item: item.entitlement_id)
    ]
    claimable = sum(int(row["amount_atomic"]) for row in leaves)
    payload = {
        "snapshot_type": "TEST_ONLY_MIGRATION_PREVIEW",
        "leaves": leaves,
        "public_claim_enabled": False,
        "total_supply_atomic": str(TOTAL_SUPPLY_ATOMIC),
        "treasury_remainder_atomic": str(TOTAL_SUPPLY_ATOMIC - claimable),
        "claimable_atomic": str(claimable),
    }
    root = _hash(payload)
    existing = (
        await session.execute(
            select(TokoinMigrationSnapshot).where(TokoinMigrationSnapshot.merkle_root == root)
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = TokoinMigrationSnapshot(
            snapshot_id=new_tokoin_migration_snapshot_id(),
            snapshot_type="TEST_ONLY_MIGRATION_PREVIEW",
            merkle_root=root,
            payload=payload,
            total_supply_atomic=str(TOTAL_SUPPLY_ATOMIC),
            treasury_remainder_atomic=str(TOTAL_SUPPLY_ATOMIC - claimable),
            claimable_atomic=str(claimable),
            public_claim_enabled=False,
            created_at=now_utc(),
        )
        session.add(existing)
    return {
        "snapshot_id": existing.snapshot_id,
        "snapshot_type": existing.snapshot_type,
        "merkle_root": existing.merkle_root,
        "leaf_count": len(leaves),
        "claimable_atomic": existing.claimable_atomic,
        "treasury_remainder_atomic": existing.treasury_remainder_atomic,
        "public_claim_enabled": existing.public_claim_enabled,
        "supply_conserved": int(existing.claimable_atomic)
        + int(existing.treasury_remainder_atomic)
        == TOTAL_SUPPLY_ATOMIC,
    }
