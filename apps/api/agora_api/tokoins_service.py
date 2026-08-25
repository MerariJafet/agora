"""TOKOIN internal economy service.

TOKOIN is an in-world coordination token, not a public cryptocurrency or a
financial instrument. The world starts with exactly 1,000,000 units held by
the AGORA treasury. Wallet balances are current-state projections; the
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
from agora_api.models import Agent, TokoinLedgerEntry, TokoinSupply, TokoinWallet

CURRENCY_CODE = "TOKOIN"
MAX_SUPPLY = 1_000_000
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
    await append_event(
        session,
        event_type="tokoin.wallet_created",
        actor={"agent_id": agent_id, "agent_version_id": agent.current_version_id},
        payload={
            "wallet_id": wallet.wallet_id,
            "currency_code": CURRENCY_CODE,
            "initial_balance": 0,
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
        "max_supply": supply.max_supply,
        "circulating_supply": int(circulating),
        "treasury_balance": treasury.balance if treasury else None,
        "wallet_count": int(wallets),
        "genesis_hash": supply.genesis_hash,
        "treasury_wallet_id": supply.treasury_wallet_id,
        "monetary_policy": "fixed_supply_no_minting_api",
    }


def wallet_view(wallet: TokoinWallet) -> dict[str, Any]:
    return {
        "wallet_id": wallet.wallet_id,
        "agent_id": wallet.agent_id,
        "label": wallet.label,
        "currency_code": CURRENCY_CODE,
        "balance": wallet.balance,
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
    if supply.max_supply != MAX_SUPPLY:
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
            "amount": amount,
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
    return entry


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
    if int(total_balance) != MAX_SUPPLY:
        return {"valid": False, "reason": "supply_mismatch", "total_balance": int(total_balance)}
    return {
        "valid": True,
        "entries": len(rows),
        "tip_hash": previous_hash,
        "total_balance": int(total_balance),
        "max_supply": MAX_SUPPLY,
    }
