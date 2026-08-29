"""MAGNA Sprint 04.4 private economic pilot API."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.db import get_session
from agora_api.magna_private_pilot import (
    authorize_and_reconcile_settlement,
    create_test_only_migration_snapshot,
    deterministic_100_agent_simulation,
    genesis_100_wallet_readiness,
    ingest_founder_ratification_receipts,
    policy_as_code,
    private_pilot_status,
    require_private_pilot_environment,
)

router = APIRouter(prefix="/v1/tokoin-private-pilot", tags=["magna-private-pilot"])


@router.get("/status")
async def get_private_pilot_status(session: AsyncSession = Depends(get_session)) -> dict:
    return await private_pilot_status(session)


@router.get("/policy")
async def get_private_pilot_policy() -> dict:
    return policy_as_code()


@router.get("/genesis-100/readiness")
async def get_genesis_100_readiness() -> dict:
    return genesis_100_wallet_readiness()


@router.post("/ratifications/ingest", status_code=201)
async def post_ratification_ingestion(session: AsyncSession = Depends(get_session)) -> dict:
    require_private_pilot_environment()
    result = await ingest_founder_ratification_receipts(session)
    await session.commit()
    return result


@router.get("/simulations/genesis-100")
async def get_genesis_100_simulation() -> dict:
    return deterministic_100_agent_simulation()


@router.post("/settlements/{settlement_plan_id}/authorize-and-reconcile", status_code=201)
async def post_authorize_and_reconcile_settlement(
    settlement_plan_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    require_private_pilot_environment()
    result = await authorize_and_reconcile_settlement(session, settlement_plan_id)
    await session.commit()
    return result


@router.post("/migration-snapshots/test-only", status_code=201)
async def post_test_only_migration_snapshot(
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_private_pilot_environment()
    result = await create_test_only_migration_snapshot(session)
    await session.commit()
    return result
