"""TOKOIN internal economy service.

TOKOIN is an in-world coordination token, not a public cryptocurrency or a
financial instrument. The world starts with exactly 1,000,000 TOKOIN held by
the AGORA treasury. Each TOKOIN is divisible into 100,000,000 aceros, the
integer ledger unit. Wallet balances are current-state projections; the
`tokoin_ledger_entries` table is append-only and hash-chained.
"""

import hashlib
import json
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.errors import AgoraError, NotFound, ValidationFailed
from agora_api.events import append_event, now_utc
from agora_api.ids import new_tokoin_block_id, new_tokoin_entry_id, new_wallet_id
from agora_api.models import (
    Agent,
    RecordProvenance,
    TokoinBlock,
    TokoinLedgerEntry,
    TokoinSupply,
    TokoinWallet,
)
from agora_api.provenance import add_provenance

CURRENCY_CODE = "TOKOIN"
ACEROS_PER_TOKOIN = 100_000_000
MAX_SUPPLY_TOKOINS = 1_000_000
MAX_SUPPLY_ACEROS = MAX_SUPPLY_TOKOINS * ACEROS_PER_TOKOIN
TREASURY_WALLET_ID = "wal_0000000000000000000TREASRY"
SYSTEM_AGENT_ID = "agt_0000000000000000000AG0RA00"
SYSTEM_VERSION_ID = "agv_0000000000000000000AG0RA01"


class InsufficientTokoins(AgoraError):
    status_code = 409
    code = "insufficient_tokoins"


def _iso_z(value) -> str:
    return value.isoformat().replace("+00:00", "Z")


def canonical_ledger_payload(entry: TokoinLedgerEntry | dict[str, Any]) -> dict[str, Any]:
    if isinstance(entry, dict):
        created_at = entry["created_at"]
        created = created_at if isinstance(created_at, str) else _iso_z(created_at)
        return {
            "sequence": entry["sequence"],
            "entry_type": entry["entry_type"],
            "from_wallet_id": entry.get("from_wallet_id"),
            "to_wallet_id": entry.get("to_wallet_id"),
            "amount": entry["amount"],
            "currency_code": entry["currency_code"],
            "reason": entry["reason"],
            "mission_id": entry.get("mission_id"),
            "event_id": entry.get("event_id"),
            "previous_hash": entry.get("previous_hash"),
            "created_at": created,
        }
    return {
        "sequence": entry.sequence,
        "entry_type": entry.entry_type,
        "from_wallet_id": entry.from_wallet_id,
        "to_wallet_id": entry.to_wallet_id,
        "amount": entry.amount,
        "currency_code": entry.currency_code,
        "reason": entry.reason,
        "mission_id": entry.mission_id,
        "event_id": entry.event_id,
        "previous_hash": entry.previous_hash,
        "created_at": _iso_z(entry.created_at),
    }


def ledger_hash(entry: TokoinLedgerEntry | dict[str, Any]) -> str:
    payload = canonical_ledger_payload(entry)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def canonical_json_hash(payload: dict[str, Any], *, domain: str) -> str:
    envelope = {"domain": domain, "payload": payload}
    raw = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def merkle_root(leaves: list[str]) -> str:
    if not leaves:
        raise ValidationFailed("Cannot calculate a Merkle root for an empty block.")
    level = leaves[:]
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [
            hashlib.sha256((level[index] + level[index + 1]).encode()).hexdigest()
            for index in range(0, len(level), 2)
        ]
    return level[0]


def canonical_block_payload(block: TokoinBlock | dict[str, Any]) -> dict[str, Any]:
    if isinstance(block, dict):
        created_at = block["created_at"]
        created = created_at if isinstance(created_at, str) else _iso_z(created_at)
        return {
            "height": block["height"],
            "first_sequence": block["first_sequence"],
            "last_sequence": block["last_sequence"],
            "entry_count": block["entry_count"],
            "transaction_merkle_root": block["transaction_merkle_root"],
            "previous_block_hash": block.get("previous_block_hash"),
            "proof_bundle_hash": block["proof_bundle_hash"],
            "created_at": created,
        }
    return {
        "height": block.height,
        "first_sequence": block.first_sequence,
        "last_sequence": block.last_sequence,
        "entry_count": block.entry_count,
        "transaction_merkle_root": block.transaction_merkle_root,
        "previous_block_hash": block.previous_block_hash,
        "proof_bundle_hash": block.proof_bundle_hash,
        "created_at": _iso_z(block.created_at),
    }


def tokoin_block_hash(block: TokoinBlock | dict[str, Any]) -> str:
    return canonical_json_hash(canonical_block_payload(block), domain="tokoin.block.v1")


async def get_supply(session: AsyncSession) -> TokoinSupply:
    supply = await session.get(TokoinSupply, CURRENCY_CODE)
    if supply is None:
        raise NotFound("TOKOIN supply has not been initialized.")
    return supply


async def treasury_wallet(session: AsyncSession, *, lock: bool = False) -> TokoinWallet:
    query = select(TokoinWallet).where(TokoinWallet.wallet_id == TREASURY_WALLET_ID)
    if lock:
        query = query.with_for_update()
    wallet = (await session.execute(query)).scalar_one_or_none()
    if wallet is None:
        raise NotFound("TOKOIN treasury wallet not found.")
    return wallet


async def wallet_for_agent(
    session: AsyncSession,
    agent_id: str,
    *,
    create: bool = False,
    trace_id: str | None = None,
) -> TokoinWallet:
    wallet = (
        await session.execute(select(TokoinWallet).where(TokoinWallet.agent_id == agent_id))
    ).scalar_one_or_none()
    if wallet is not None:
        return wallet
    if not create:
        raise NotFound("Agent wallet not found.")
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise NotFound("Agent not found.")
    agent_provenance = await session.get(RecordProvenance, ("agents", agent_id))
    provenance_kwargs = {}
    if (
        agent_provenance is not None
        and agent_provenance.provenance_class in {"real", "demo", "test"}
    ):
        provenance_kwargs = {
            "provenance_class": agent_provenance.provenance_class,
            "environment_id": agent_provenance.environment_id,
            "run_id": agent_provenance.run_id,
            "world_instance_id": agent_provenance.world_instance_id,
            "created_by_actor_id": agent_id,
            "created_by_actor_provenance": agent_provenance.provenance_class,
        }
    ts = now_utc()
    wallet = TokoinWallet(
        wallet_id=new_wallet_id(),
        agent_id=agent_id,
        label=f"{agent.name} TOKOIN Wallet",
        balance=0,
        created_at=ts,
        updated_at=ts,
    )
    session.add(wallet)
    await add_provenance(
        session,
        record_table="tokoin_wallets",
        record_id=wallet.wallet_id,
        created_by="tokoin.wallet_for_agent",
        source_reference=agent_id,
        **provenance_kwargs,
    )
    await append_event(
        session,
        event_type="tokoin.wallet_created",
        actor={"agent_id": agent_id, "agent_version_id": agent.current_version_id},
        payload={
            "wallet_id": wallet.wallet_id,
            "currency_code": CURRENCY_CODE,
            "unit": "acero",
            "initial_balance_aceros": 0,
            "agent_must_self_configure_wallet": True,
        },
        trace_id=trace_id,
    )
    return wallet


async def tokoin_status(session: AsyncSession) -> dict[str, Any]:
    supply = await get_supply(session)
    wallets = (
        await session.execute(select(func.count(TokoinWallet.wallet_id)))
    ).scalar_one()
    circulating = (
        await session.execute(
            select(func.coalesce(func.sum(TokoinWallet.balance), 0)).where(
                TokoinWallet.wallet_id != supply.treasury_wallet_id
            )
        )
    ).scalar_one()
    treasury = await session.get(TokoinWallet, supply.treasury_wallet_id)
    blockchain = await verify_tokoin_blockchain(session)
    return {
        "currency_code": CURRENCY_CODE,
        "unit": "acero",
        "aceros_per_tokoin": ACEROS_PER_TOKOIN,
        "max_supply": MAX_SUPPLY_TOKOINS,
        "max_supply_aceros": supply.max_supply,
        "circulating_supply": int(circulating) / ACEROS_PER_TOKOIN,
        "circulating_supply_aceros": int(circulating),
        "treasury_balance": (
            treasury.balance / ACEROS_PER_TOKOIN if treasury else None
        ),
        "treasury_balance_aceros": treasury.balance if treasury else None,
        "wallet_count": int(wallets),
        "genesis_hash": supply.genesis_hash,
        "treasury_wallet_id": supply.treasury_wallet_id,
        "monetary_policy": "fixed_supply_100000000_aceros_per_tokoin_no_minting_api",
        "blockchain": {
            "valid": blockchain["valid"],
            "blocks": blockchain.get("blocks", 0),
            "sealed_entries": blockchain.get("sealed_entries", 0),
            "pending_entries": blockchain.get("pending_entries", 0),
            "tip_hash": blockchain.get("tip_hash"),
        },
    }


async def wallet_population_audit(session: AsyncSession) -> dict[str, Any]:
    """Read-only wallet population and fixed-supply audit.

    This endpoint is intentionally operational metadata only: it reports counts,
    provenance classes and chain validity without returning wallet balances per
    Agent or any private runtime data.
    """
    total_wallets = int(
        (await session.execute(select(func.count(TokoinWallet.wallet_id)))).scalar_one()
    )
    agent_wallets = int(
        (
            await session.execute(
                select(func.count(TokoinWallet.wallet_id)).where(TokoinWallet.agent_id.is_not(None))
            )
        ).scalar_one()
    )
    treasury_wallets = int(
        (
            await session.execute(
                select(func.count(TokoinWallet.wallet_id)).where(TokoinWallet.agent_id.is_(None))
            )
        ).scalar_one()
    )
    total_balance = int(
        (
            await session.execute(select(func.coalesce(func.sum(TokoinWallet.balance), 0)))
        ).scalar_one()
    )
    duplicate_subquery = (
        select(TokoinWallet.agent_id)
        .where(TokoinWallet.agent_id.is_not(None))
        .group_by(TokoinWallet.agent_id)
        .having(func.count(TokoinWallet.wallet_id) > 1)
        .subquery()
    )
    duplicate_groups = int(
        (await session.execute(select(func.count()).select_from(duplicate_subquery))).scalar_one()
    )
    provenance_subquery = (
        select(
            func.coalesce(RecordProvenance.provenance_class, "missing").label("bucket"),
        )
        .select_from(TokoinWallet)
        .join(
            RecordProvenance,
            (RecordProvenance.record_table == "tokoin_wallets")
            & (RecordProvenance.record_id == TokoinWallet.wallet_id),
            isouter=True,
        )
        .subquery()
    )
    provenance_rows = (
        await session.execute(
            select(provenance_subquery.c.bucket, func.count())
            .group_by(provenance_subquery.c.bucket)
            .order_by(provenance_subquery.c.bucket)
        )
    ).all()
    world_subquery = (
        select(
            func.coalesce(RecordProvenance.world_instance_id, "missing").label("bucket"),
        )
        .select_from(TokoinWallet)
        .join(
            RecordProvenance,
            (RecordProvenance.record_table == "tokoin_wallets")
            & (RecordProvenance.record_id == TokoinWallet.wallet_id),
            isouter=True,
        )
        .subquery()
    )
    world_rows = (
        await session.execute(
            select(world_subquery.c.bucket, func.count())
            .group_by(world_subquery.c.bucket)
            .order_by(world_subquery.c.bucket)
        )
    ).all()
    chain = await verify_ledger_chain(session)
    return {
        "wallets_total": total_wallets,
        "agent_wallets": agent_wallets,
        "treasury_wallets": treasury_wallets,
        "duplicate_agent_wallet_groups": duplicate_groups,
        "total_balance_aceros": total_balance,
        "max_supply_aceros": MAX_SUPPLY_ACEROS,
        "supply_conserved": total_balance == MAX_SUPPLY_ACEROS,
        "ledger_chain": chain,
        "blockchain": await verify_tokoin_blockchain(session),
        "by_provenance_class": {str(key): int(value) for key, value in provenance_rows},
        "by_world_instance_id": {str(key): int(value) for key, value in world_rows},
        "classification": (
            "read_only_population_audit_unknown_rows_are_legacy_debt_not_reclassified"
        ),
    }


def tokoin_block_view(block: TokoinBlock) -> dict[str, Any]:
    return {
        "block_id": block.block_id,
        "height": block.height,
        "first_sequence": block.first_sequence,
        "last_sequence": block.last_sequence,
        "entry_count": block.entry_count,
        "transaction_merkle_root": block.transaction_merkle_root,
        "previous_block_hash": block.previous_block_hash,
        "block_hash": block.block_hash,
        "proof_bundle_hash": block.proof_bundle_hash,
        "proof_bundle": block.proof_bundle,
        "created_at": _iso_z(block.created_at),
    }


async def _last_block(session: AsyncSession, *, lock: bool = False) -> TokoinBlock | None:
    query = select(TokoinBlock).order_by(TokoinBlock.height.desc()).limit(1)
    if lock:
        query = query.with_for_update()
    return (await session.execute(query)).scalar_one_or_none()


def _entry_proof(entry: TokoinLedgerEntry) -> dict[str, Any]:
    return {
        "sequence": entry.sequence,
        "entry_id": entry.entry_id,
        "entry_type": entry.entry_type,
        "entry_hash": entry.entry_hash,
        "event_id": entry.event_id,
        "mission_id": entry.mission_id,
        "from_wallet_id": entry.from_wallet_id,
        "to_wallet_id": entry.to_wallet_id,
        "amount_aceros": entry.amount,
        "currency_code": entry.currency_code,
        "reason": entry.reason,
        "created_at": _iso_z(entry.created_at),
    }


def _block_proof_bundle(entries: list[TokoinLedgerEntry]) -> dict[str, Any]:
    return {
        "schema": "agora.tokoin.block_proof_bundle.v1",
        "currency_code": CURRENCY_CODE,
        "unit": "acero",
        "aceros_per_tokoin": ACEROS_PER_TOKOIN,
        "max_supply_aceros": MAX_SUPPLY_ACEROS,
        "paper_binding_policy": (
            "Blocks bind reward entries to mission_id/event_id/artifact references; "
            "paper bytes remain in ArtifactVersion content hashes, not inside TOKOIN."
        ),
        "entries": [_entry_proof(entry) for entry in entries],
    }


async def seal_pending_tokoin_block(
    session: AsyncSession,
    *,
    max_entries: int = 500,
    trace_id: str | None = None,
) -> tuple[TokoinBlock | None, bool]:
    """Seal pending ledger entries into one append-only block.

    This is intentionally not minting and not consensus. It is a deterministic
    transparency-log block over already-committed TOKOIN ledger entries.
    """
    if max_entries < 1 or max_entries > 5000:
        raise ValidationFailed("max_entries must be between 1 and 5000.")
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext('agora_tokoin_blocks_v1'))"))
    last = await _last_block(session, lock=True)
    after_sequence = last.last_sequence if last else 0
    entry_result = await session.execute(
        select(TokoinLedgerEntry)
        .where(TokoinLedgerEntry.sequence > after_sequence)
        .order_by(TokoinLedgerEntry.sequence)
        .limit(max_entries)
    )
    entries = list(entry_result.scalars().all())
    if not entries:
        return last, False
    expected_first = after_sequence + 1
    if entries[0].sequence != expected_first:
        raise ValidationFailed("TOKOIN ledger has an unsealable sequence gap.")
    for previous, current in zip(entries, entries[1:], strict=False):
        if current.sequence != previous.sequence + 1:
            raise ValidationFailed("TOKOIN block entries must be contiguous.")
    entry_hashes = [entry.entry_hash for entry in entries]
    proof_bundle = _block_proof_bundle(entries)
    proof_bundle_hash = canonical_json_hash(
        proof_bundle, domain="tokoin.block_proof_bundle.v1"
    )
    ts = now_utc()
    block_data = {
        "height": (last.height + 1) if last else 1,
        "first_sequence": entries[0].sequence,
        "last_sequence": entries[-1].sequence,
        "entry_count": len(entries),
        "transaction_merkle_root": merkle_root(entry_hashes),
        "previous_block_hash": last.block_hash if last else None,
        "proof_bundle_hash": proof_bundle_hash,
        "created_at": ts,
    }
    block = TokoinBlock(
        block_id=new_tokoin_block_id(),
        block_hash=tokoin_block_hash(block_data),
        proof_bundle=proof_bundle,
        **block_data,
    )
    session.add(block)
    await add_provenance(
        session,
        record_table="tokoin_blocks",
        record_id=block.block_id,
        created_by="tokoin.seal_pending_tokoin_block",
        source_reference=f"{block.first_sequence}:{block.last_sequence}",
    )
    await append_event(
        session,
        event_type="tokoin.block_sealed",
        actor={"agent_id": SYSTEM_AGENT_ID, "agent_version_id": SYSTEM_VERSION_ID},
        payload={
            "block_id": block.block_id,
            "height": block.height,
            "first_sequence": block.first_sequence,
            "last_sequence": block.last_sequence,
            "entry_count": block.entry_count,
            "transaction_merkle_root": block.transaction_merkle_root,
            "block_hash": block.block_hash,
            "previous_block_hash": block.previous_block_hash,
            "proof_bundle_hash": block.proof_bundle_hash,
            "currency_code": CURRENCY_CODE,
            "unit": "acero",
        },
        trace_id=trace_id,
    )
    return block, True


async def verify_tokoin_blockchain(session: AsyncSession) -> dict[str, Any]:
    blocks = (
        await session.execute(select(TokoinBlock).order_by(TokoinBlock.height))
    ).scalars().all()
    previous_block_hash = None
    expected_first_sequence = 1
    for expected_height, block in enumerate(blocks, start=1):
        if block.height != expected_height:
            return {"valid": False, "reason": "block_height_gap", "block_id": block.block_id}
        if block.first_sequence != expected_first_sequence:
            return {"valid": False, "reason": "block_sequence_gap", "block_id": block.block_id}
        if block.previous_block_hash != previous_block_hash:
            return {
                "valid": False,
                "reason": "previous_block_hash_mismatch",
                "block_id": block.block_id,
            }
        entry_result = await session.execute(
            select(TokoinLedgerEntry)
            .where(
                TokoinLedgerEntry.sequence >= block.first_sequence,
                TokoinLedgerEntry.sequence <= block.last_sequence,
            )
            .order_by(TokoinLedgerEntry.sequence)
        )
        entries = list(entry_result.scalars().all())
        if len(entries) != block.entry_count:
            return {"valid": False, "reason": "block_entry_count_mismatch",
                    "block_id": block.block_id}
        for entry in entries:
            if ledger_hash(entry) != entry.entry_hash:
                return {"valid": False, "reason": "entry_hash_mismatch",
                        "entry_id": entry.entry_id}
        entry_hashes = [entry.entry_hash for entry in entries]
        if merkle_root(entry_hashes) != block.transaction_merkle_root:
            return {"valid": False, "reason": "merkle_root_mismatch",
                    "block_id": block.block_id}
        proof_bundle = _block_proof_bundle(entries)
        if (
            canonical_json_hash(proof_bundle, domain="tokoin.block_proof_bundle.v1")
            != block.proof_bundle_hash
        ):
            return {"valid": False, "reason": "proof_bundle_hash_mismatch",
                    "block_id": block.block_id}
        if tokoin_block_hash(block) != block.block_hash:
            return {"valid": False, "reason": "block_hash_mismatch",
                    "block_id": block.block_id}
        previous_block_hash = block.block_hash
        expected_first_sequence = block.last_sequence + 1
    ledger_entries = int(
        (await session.execute(select(func.count(TokoinLedgerEntry.entry_id)))).scalar_one()
    )
    sealed_entries = expected_first_sequence - 1
    return {
        "valid": True,
        "scheme": "tokoin_hash_chain_merkle_blocks_v1",
        "blocks": len(blocks),
        "sealed_entries": sealed_entries,
        "pending_entries": max(ledger_entries - sealed_entries, 0),
        "tip_hash": previous_block_hash,
        "currency_code": CURRENCY_CODE,
        "unit": "acero",
        "aceros_per_tokoin": ACEROS_PER_TOKOIN,
        "max_supply_aceros": MAX_SUPPLY_ACEROS,
        "security_model": "tamper_evident_internal_testnet_not_public_consensus",
    }


def wallet_view(wallet: TokoinWallet) -> dict[str, Any]:
    return {
        "wallet_id": wallet.wallet_id,
        "agent_id": wallet.agent_id,
        "label": wallet.label,
        "currency_code": CURRENCY_CODE,
        "unit": "acero",
        "aceros_per_tokoin": ACEROS_PER_TOKOIN,
        "balance": wallet.balance / ACEROS_PER_TOKOIN,
        "balance_aceros": wallet.balance,
        "created_at": _iso_z(wallet.created_at),
        "updated_at": _iso_z(wallet.updated_at),
    }


async def _last_entry(session: AsyncSession, *, lock: bool = False) -> TokoinLedgerEntry:
    query = select(TokoinLedgerEntry).order_by(TokoinLedgerEntry.sequence.desc()).limit(1)
    if lock:
        query = query.with_for_update()
    entry = (await session.execute(query)).scalar_one_or_none()
    if entry is None:
        raise NotFound("TOKOIN ledger has no genesis entry.")
    return entry


async def transfer_from_treasury(
    session: AsyncSession,
    *,
    to_agent_id: str,
    amount: int,
    reason: str,
    mission_id: str | None = None,
    trace_id: str | None = None,
) -> TokoinLedgerEntry:
    if amount <= 0:
        raise ValidationFailed("TOKOIN amount must be positive.")
    if len(reason) > 128:
        raise ValidationFailed("TOKOIN reason is too long.")
    supply = await get_supply(session)
    if supply.max_supply != MAX_SUPPLY_ACEROS:
        raise ValidationFailed("TOKOIN fixed supply invariant failed.")
    treasury = await treasury_wallet(session, lock=True)
    target = await wallet_for_agent(session, to_agent_id, create=True, trace_id=trace_id)
    # Lock the target row after create/load. Flush first so a newly-created
    # wallet exists before we query it with FOR UPDATE.
    await session.flush()
    target = (
        await session.execute(
            select(TokoinWallet)
            .where(TokoinWallet.wallet_id == target.wallet_id)
            .with_for_update()
        )
    ).scalar_one()
    if treasury.balance < amount:
        raise InsufficientTokoins("TOKOIN treasury cannot cover this transfer.")

    agent = await session.get(Agent, to_agent_id)
    assert agent is not None
    event = await append_event(
        session,
        event_type="tokoin.mission_reward",
        actor={"agent_id": to_agent_id, "agent_version_id": agent.current_version_id},
        payload={
            "wallet_id": target.wallet_id,
            "amount_aceros": amount,
            "currency_code": CURRENCY_CODE,
            "reason": reason,
            "mission_id": mission_id,
            "source": "agora_world_treasury",
        },
        trace_id=trace_id,
    )
    await session.flush()
    last = await _last_entry(session, lock=True)
    ts = now_utc()
    entry_data = {
        "sequence": last.sequence + 1,
        "entry_type": "mission_reward",
        "from_wallet_id": treasury.wallet_id,
        "to_wallet_id": target.wallet_id,
        "amount": amount,
        "currency_code": CURRENCY_CODE,
        "reason": reason,
        "mission_id": mission_id,
        "event_id": event.event_id,
        "previous_hash": last.entry_hash,
        "created_at": ts,
    }
    entry = TokoinLedgerEntry(
        entry_id=new_tokoin_entry_id(),
        entry_hash=ledger_hash(entry_data),
        **entry_data,
    )
    treasury.balance -= amount
    treasury.updated_at = ts
    target.balance += amount
    target.updated_at = ts
    session.add(entry)
    await add_provenance(
        session,
        record_table="tokoin_ledger_entries",
        record_id=entry.entry_id,
        created_by="tokoin.transfer_from_treasury",
        source_reference=mission_id,
    )
    return entry


async def transfer_one_tokoin_reward(
    session: AsyncSession,
    *,
    to_agent_id: str,
    reason: str,
    mission_id: str | None = None,
    trace_id: str | None = None,
) -> TokoinLedgerEntry:
    return await transfer_from_treasury(
        session,
        to_agent_id=to_agent_id,
        amount=ACEROS_PER_TOKOIN,
        reason=reason,
        mission_id=mission_id,
        trace_id=trace_id,
    )


async def verify_ledger_chain(session: AsyncSession) -> dict[str, Any]:
    rows = (
        await session.execute(select(TokoinLedgerEntry).order_by(TokoinLedgerEntry.sequence))
    ).scalars().all()
    previous_hash = None
    for index, entry in enumerate(rows, start=1):
        if entry.sequence != index:
            return {"valid": False, "reason": "sequence_gap", "entry_id": entry.entry_id}
        if entry.previous_hash != previous_hash:
            return {"valid": False, "reason": "previous_hash_mismatch", "entry_id": entry.entry_id}
        if ledger_hash(entry) != entry.entry_hash:
            return {"valid": False, "reason": "entry_hash_mismatch", "entry_id": entry.entry_id}
        previous_hash = entry.entry_hash
    total_balance = (
        await session.execute(select(func.coalesce(func.sum(TokoinWallet.balance), 0)))
    ).scalar_one()
    if int(total_balance) != MAX_SUPPLY_ACEROS:
        return {"valid": False, "reason": "supply_mismatch", "total_balance": int(total_balance)}
    return {
        "valid": True,
        "entries": len(rows),
        "tip_hash": previous_hash,
        "total_balance": int(total_balance),
        "max_supply": MAX_SUPPLY_ACEROS,
        "unit": "acero",
        "aceros_per_tokoin": ACEROS_PER_TOKOIN,
    }
