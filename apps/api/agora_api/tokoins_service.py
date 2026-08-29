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

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.errors import AgoraError, NotFound, ValidationFailed
from agora_api.events import append_event, now_utc
from agora_api.ids import new_tokoin_entry_id, new_wallet_id
from agora_api.models import Agent, RecordProvenance, TokoinLedgerEntry, TokoinSupply, TokoinWallet
from agora_api.provenance import add_provenance

CURRENCY_CODE = "TOKOIN"
ACEROS_PER_TOKOIN = 100_000_000
MAX_SUPPLY_TOKOINS = 1_000_000
MAX_SUPPLY_ACEROS = MAX_SUPPLY_TOKOINS * ACEROS_PER_TOKOIN
TREASURY_WALLET_ID = "wal_0000000000000000000TREASRY"


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
        "by_provenance_class": {str(key): int(value) for key, value in provenance_rows},
        "by_world_instance_id": {str(key): int(value) for key, value in world_rows},
        "classification": (
            "read_only_population_audit_unknown_rows_are_legacy_debt_not_reclassified"
        ),
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
