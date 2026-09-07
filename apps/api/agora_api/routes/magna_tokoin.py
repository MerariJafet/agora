"""MAGNA Sprint 04 TOKOIN local-devnet API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.db import get_session
from agora_api.errors import NotFound
from agora_api.magna_tokoin_testnet import (
    anchor_knowledge_root,
    assert_allowed_chain,
    bind_wallet,
    confirm_local_reservation,
    create_or_get_local_manifest,
    create_settlement_plan,
    get_local_manifest,
    knowledge_root_view,
    manifest_preview_view,
    manifest_view,
    public_testnet_readiness_view,
    ratification_bundle_view,
    release_manifest_draft_view,
    reservation_view,
    scope_matrix_view,
    settlement_plan_view,
    wallet_binding_view,
)
from agora_api.models import (
    Agent,
    TokoinDeploymentManifest,
    TokoinKnowledgeRootAnchor,
    TokoinReservation,
    TokoinSettlementPlan,
    TokoinWalletBinding,
)
from agora_api.owners import MutatingOwner
from agora_api.ratelimit import enforce_rate_limit

router = APIRouter(prefix="/v1/tokoin-testnet", tags=["magna-tokoin-testnet"])


async def _agent(session: AsyncSession, device: CurrentDevice) -> Agent:
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    return agent


@router.get("/status")
async def status(session: AsyncSession = Depends(get_session)) -> dict:
    manifest = await get_local_manifest(session)
    ratifications = ratification_bundle_view()
    ratifications_complete = ratifications["status"] == "COMPLETE"
    reservations = (
        await session.execute(select(TokoinReservation.state, TokoinReservation.amount_atomic))
    ).all()
    reserved = sum(
        int(amount)
        for state, amount in reservations
        if state in {"RESERVED", "RELEASED_ACTIVE"}
    )
    claimable = (
        await session.execute(
            select(TokoinSettlementPlan).where(TokoinSettlementPlan.state == "ALLOCATED")
        )
    ).scalars().all()
    public_readiness = public_testnet_readiness_view()
    return {
        "status": (
            "PUBLIC_TESTNET_DEPLOYED"
            if public_readiness["base_sepolia_deployed"]
            else "BLOCKED_EXTERNAL_AUDIT"
        ),
        "maximum_authorized_network": "LOCAL_DEVNET",
        "human_ratifications_complete": ratifications_complete,
        "external_independent_audit_complete": public_readiness["independent_audit"][
            "complete"
        ],
        "legacy_balances_migrated": False,
        "real_value_moved": False,
        "mainnet_transactions": 0,
        "deployment": manifest_view(manifest) if manifest else manifest_preview_view(),
        "accounting": {
            "reserved_atomic": str(reserved),
            "settlement_plan_count": len(claimable),
        },
        "scope_matrix": {
            "status": "COMPLETE_LOCAL_CLASSIFICATION",
            "missing_blockers": 0,
        },
        "ratification_gate": {
            "required_decisions": 8,
            "pending_decisions": 0 if ratifications_complete else 8,
        },
        "public_testnet": public_readiness,
        "blocked_next_step": public_readiness["next_human_gate"],
    }


@router.get("/public-readiness")
async def get_public_readiness() -> dict:
    return public_testnet_readiness_view()


@router.get("/scope-matrix")
async def get_scope_matrix() -> dict:
    return scope_matrix_view()


@router.get("/ratification-bundle")
async def get_ratification_bundle() -> dict:
    return ratification_bundle_view()


@router.get("/release-manifest")
async def get_release_manifest() -> dict:
    return release_manifest_draft_view()


@router.post("/deployment/local-devnet", status_code=201)
async def post_local_deployment(
    owner: MutatingOwner, session: AsyncSession = Depends(get_session)
) -> dict:
    await enforce_rate_limit("tokoin_control_plane", owner.user_id)
    manifest = await create_or_get_local_manifest(session)
    await session.commit()
    return manifest_view(manifest)


@router.post("/deployment/guard")
async def post_deployment_guard(request: Request, owner: MutatingOwner) -> dict:
    from agora_api.boundary import validate_boundary
    from agora_api.magna_tokoin_testnet import require_local_control_plane

    require_local_control_plane()
    await enforce_rate_limit("tokoin_control_plane", owner.user_id)
    body = await request.json()
    validate_boundary("tokoins.schema.json", "/$defs/DeploymentGuardRequest", body)
    chain_id = body["chain_id"]
    assert_allowed_chain(chain_id, require_ratification=True)
    return {"allowed": True, "chain_id": chain_id}


@router.get("/deployment/manifests")
async def list_manifests(session: AsyncSession = Depends(get_session)) -> dict:
    rows = (
        await session.execute(
            select(TokoinDeploymentManifest)
            .order_by(desc(TokoinDeploymentManifest.created_at))
            .limit(20)
        )
    ).scalars().all()
    return {"manifests": [manifest_view(row) for row in rows]}


@router.post("/wallet-bindings", status_code=201)
async def post_wallet_binding(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("tokoin_testnet_wallet_binding", device.agent_id)
    row = await bind_wallet(
        session,
        actor=await _agent(session, device),
        payload=await request.json(),
    )
    await session.commit()
    return wallet_binding_view(row)


@router.get("/wallet-bindings")
async def list_wallet_bindings(session: AsyncSession = Depends(get_session)) -> dict:
    rows = (
        await session.execute(
            select(TokoinWalletBinding).order_by(desc(TokoinWalletBinding.created_at)).limit(100)
        )
    ).scalars().all()
    return {"wallet_bindings": [wallet_binding_view(row) for row in rows]}


@router.post("/reservations", status_code=201)
async def post_reservation(
    request: Request,
    owner: MutatingOwner,
    session: AsyncSession = Depends(get_session),
) -> dict:
    from agora_api.magna_tokoin_testnet import request_reservation

    await enforce_rate_limit("tokoin_control_plane", owner.user_id)
    row = await request_reservation(
        session, await request.json(), owner_id=owner.user_id
    )
    await session.commit()
    return reservation_view(row)


@router.post("/reservations/{reservation_id}/confirm-local", status_code=201)
async def post_confirm_reservation(
    reservation_id: str,
    owner: MutatingOwner,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("tokoin_control_plane", owner.user_id)
    row = await confirm_local_reservation(
        session, reservation_id, owner_id=owner.user_id
    )
    await session.commit()
    return reservation_view(row)


@router.get("/reservations/{reservation_id}")
async def get_reservation(
    reservation_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    row = await session.get(TokoinReservation, reservation_id)
    if row is None:
        raise NotFound("TOKOIN reservation not found.")
    return reservation_view(row)


@router.post("/settlement-plans", status_code=201)
async def post_settlement_plan(
    request: Request,
    owner: MutatingOwner,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("tokoin_control_plane", owner.user_id)
    row = await create_settlement_plan(
        session, await request.json(), owner_id=owner.user_id
    )
    await session.commit()
    return settlement_plan_view(row)


@router.get("/settlement-plans/{settlement_plan_id}")
async def get_settlement_plan(
    settlement_plan_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    row = await session.get(TokoinSettlementPlan, settlement_plan_id)
    if row is None:
        raise NotFound("TOKOIN settlement plan not found.")
    return settlement_plan_view(row)


@router.post("/knowledge-roots", status_code=201)
async def post_knowledge_root(
    request: Request,
    owner: MutatingOwner,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("tokoin_control_plane", owner.user_id)
    row = await anchor_knowledge_root(session, await request.json())
    await session.commit()
    return knowledge_root_view(row)


@router.get("/knowledge-roots")
async def list_knowledge_roots(session: AsyncSession = Depends(get_session)) -> dict:
    rows = (
        await session.execute(
            select(TokoinKnowledgeRootAnchor)
            .order_by(desc(TokoinKnowledgeRootAnchor.created_at))
            .limit(50)
        )
    ).scalars().all()
    return {"knowledge_roots": [knowledge_root_view(row) for row in rows]}
