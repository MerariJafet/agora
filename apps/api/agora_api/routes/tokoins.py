"""TOKOIN internal economy API."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.boundary import validate_boundary
from agora_api.db import get_session
from agora_api.errors import NotFound, OwnerAuthorityRequired
from agora_api.models import Mission, MissionParticipant, TokoinLedgerEntry
from agora_api.ratelimit import enforce_rate_limit
from agora_api.tokoins_service import (
    ACEROS_PER_TOKOIN,
    tokoin_status,
    transfer_from_treasury,
    verify_ledger_chain,
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


@router.get("/v1/tokoins/ledger")
async def list_tokoin_ledger(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    rows = (
        await session.execute(
            select(TokoinLedgerEntry)
            .order_by(TokoinLedgerEntry.sequence.desc())
            .limit(limit)
        )
    ).scalars().all()
    verification = await verify_ledger_chain(session)
    return {"ledger": [ledger_entry_view(row) for row in rows], "verification": verification}


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
