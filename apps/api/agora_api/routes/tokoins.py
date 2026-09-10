"""TOKOIN internal economy API."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.boundary import validate_boundary
from agora_api.config import get_settings
from agora_api.db import get_session
from agora_api.errors import Conflict, NotFound, OwnerAuthorityRequired
from agora_api.models import Mission, MissionParticipant, TokoinLedgerEntry
from agora_api.ratelimit import enforce_rate_limit
from agora_api.tokoins_service import (
    ACEROS_PER_TOKOIN,
    seal_pending_tokoin_block,
    signed_transfer_message,
    signed_wallet_transfer,
    tokoin_block_view,
    tokoin_chain_export,
    tokoin_status,
    transfer_from_treasury,
    verify_ledger_chain,
    verify_tokoin_blockchain,
    wallet_for_agent,
    wallet_population_audit,
    wallet_view,
)

router = APIRouter(tags=["tokoins"])


def ledger_entry_view(entry: TokoinLedgerEntry) -> dict:
    return {
        "entry_id": entry.entry_id,
        "sequence": entry.sequence,
        "entry_type": entry.entry_type,
        "from_wallet_id": entry.from_wallet_id,
        "to_wallet_id": entry.to_wallet_id,
        "amount": entry.amount / ACEROS_PER_TOKOIN,
        "amount_aceros": entry.amount,
        "currency_code": entry.currency_code,
        "unit": "acero",
        "reason": entry.reason,
        "mission_id": entry.mission_id,
        "event_id": entry.event_id,
        "previous_hash": entry.previous_hash,
        "entry_hash": entry.entry_hash,
        "created_at": entry.created_at.isoformat().replace("+00:00", "Z"),
    }


@router.get("/v1/tokoins/status")
async def get_tokoin_status(session: AsyncSession = Depends(get_session)) -> dict:
    return await tokoin_status(session)


@router.get("/v1/tokoins/balances")
async def get_tokoin_balances(session: AsyncSession = Depends(get_session)) -> dict:
    """Return public aggregate balances without exposing any agent wallet balance."""
    status = await tokoin_status(session)
    return {
        "currency_code": status["currency_code"],
        "unit": status["unit"],
        "aceros_per_tokoin": status["aceros_per_tokoin"],
        "max_supply": status["max_supply"],
        "max_supply_aceros": status["max_supply_aceros"],
        "balances": {
            "treasury": {
                "balance": status["treasury_balance"],
                "balance_aceros": status["treasury_balance_aceros"],
            },
            "circulating": {
                "balance": status["circulating_supply"],
                "balance_aceros": status["circulating_supply_aceros"],
            },
        },
        "wallet_count": status["wallet_count"],
        "balance_scope": "aggregate_only",
        "per_wallet_balances_exposed": False,
        "blockchain": status["blockchain"],
    }


@router.get("/v1/tokoins/ledger")
async def list_tokoin_ledger(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    rows = (
        (
            await session.execute(
                select(TokoinLedgerEntry).order_by(TokoinLedgerEntry.sequence.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    verification = await verify_ledger_chain(session)
    return {"ledger": [ledger_entry_view(row) for row in rows], "verification": verification}


@router.get("/v1/tokoins/blockchain")
async def get_tokoin_blockchain(session: AsyncSession = Depends(get_session)) -> dict:
    return {"verification": await verify_tokoin_blockchain(session)}


@router.get("/v1/tokoins/blockchain/export")
async def export_tokoin_blockchain(
    session: AsyncSession = Depends(get_session),
    limit_entries: int = Query(default=200, ge=1, le=1000),
) -> dict:
    return await tokoin_chain_export(session, limit_entries=limit_entries)


@router.post("/v1/tokoins/blockchain/seal", status_code=201)
async def seal_tokoin_blockchain(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("tokoin_block_seal", device.agent_id)
    block, sealed = await seal_pending_tokoin_block(
        session,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return {
        "sealed": sealed,
        "block": tokoin_block_view(block) if block else None,
        "verification": await verify_tokoin_blockchain(session),
        "economic_effect": "none_no_mint_no_transfer",
    }


@router.get("/v1/agents/me/wallet")
async def get_my_wallet(
    device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    return wallet_view(await wallet_for_agent(session, device.agent_id))


@router.get("/v1/agents/{agent_id}/wallet")
async def get_agent_wallet(agent_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    return wallet_view(await wallet_for_agent(session, agent_id))


@router.post("/v1/agents/me/wallet/provision", status_code=201)
async def provision_my_wallet(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("tokoin_wallet_provision", device.agent_id)
    existing = True
    try:
        wallet = await wallet_for_agent(session, device.agent_id)
    except NotFound:
        existing = False
        wallet = await wallet_for_agent(
            session,
            device.agent_id,
            create=True,
            trace_id=getattr(request.state, "trace_id", None),
        )
        await session.commit()
    return wallet_view(wallet) | {
        "created": not existing,
        "real_balance_changed": False,
        "provisioning_policy": "idempotent_zero_balance_wallet_only",
    }


@router.post("/v1/agents/me/wallet/transfer-message")
async def post_transfer_message(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_boundary("tokoins.schema.json", "/$defs/WalletTransferIntentRequest", body)
    source = await wallet_for_agent(session, device.agent_id)
    message = signed_transfer_message(
        from_wallet_id=source.wallet_id,
        to_wallet_id=body["to_wallet_id"],
        amount=body["amount"],
        reason=body["reason"],
        nonce=body["nonce"],
    )
    return {
        "context": "agora.tokoin.transfer.v1",
        "from_wallet_id": source.wallet_id,
        "to_wallet_id": body["to_wallet_id"],
        "amount_aceros": body["amount"],
        "currency_code": "TOKOIN",
        "reason": body["reason"],
        "nonce": body["nonce"],
        "canonical_message": message.decode(),
    }


@router.post("/v1/agents/me/wallet/transfers", status_code=201)
async def post_signed_wallet_transfer(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("tokoin_wallet_transfer", device.agent_id)
    body = await request.json()
    validate_boundary("tokoins.schema.json", "/$defs/SignedWalletTransferEnvelope", body)
    entry = await signed_wallet_transfer(
        session,
        signer_device=device,
        to_wallet_id=body["to_wallet_id"],
        amount=body["amount"],
        reason=body["reason"],
        nonce=body["nonce"],
        signature=body["signature"],
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return ledger_entry_view(entry)


@router.get("/v1/tokoins/wallet-audit")
async def get_wallet_audit(session: AsyncSession = Depends(get_session)) -> dict:
    return await wallet_population_audit(session)


@router.post("/v1/missions/{mission_id}/tokoin-rewards", status_code=201)
async def post_mission_reward(
    mission_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    settings = get_settings()
    if settings.is_production:
        raise Conflict("Legacy TOKOIN treasury rewards are disabled in production.")
    if device.agent_id not in settings.tokoin_reward_admin_agent_ids:
        raise OwnerAuthorityRequired(
            "TOKOIN treasury rewards require an explicitly authorized operator."
        )
    await enforce_rate_limit("tokoin_mission_reward", device.agent_id)
    body = await request.json()
    validate_boundary("tokoins.schema.json", "/$defs/MissionRewardRequest", body)
    mission = await session.get(Mission, mission_id)
    if mission is None:
        raise NotFound("Mission not found.")
    if mission.created_by_agent_id != device.agent_id:
        raise OwnerAuthorityRequired("Only the Mission creator may assign TOKOIN rewards.")
    participant = await session.get(MissionParticipant, (mission_id, body["agent_id"]))
    if participant is None or participant.left_at is not None:
        raise OwnerAuthorityRequired("TOKOIN rewards are limited to Mission participants.")
    entry = await transfer_from_treasury(
        session,
        to_agent_id=body["agent_id"],
        amount=body["amount"],
        reason=body["reason"],
        mission_id=mission_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return ledger_entry_view(entry)
