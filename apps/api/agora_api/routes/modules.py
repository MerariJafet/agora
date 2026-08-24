"""World Builder / Modules API (Sprint 08)."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.db import get_session
from agora_api.errors import NotFound
from agora_api.models import (
    BuildProposal,
    Game,
    GameVersion,
    Module,
    ModuleVersion,
    WorldPlot,
)
from agora_api.modules_service import (
    create_build_proposal,
    create_game_session,
    create_module_update,
    module_view,
    plot_view,
    proposal_view,
    publish_module,
    review_module_version,
    review_view,
    rollback_module,
    session_view,
    set_plot_runtime,
    validate_create_build_proposal,
    validate_game_session,
    validate_review_module,
    version_view,
)
from agora_api.ratelimit import enforce_rate_limit
from agora_api.realtime import gateway

router = APIRouter(tags=["modules"])


async def _module(session: AsyncSession, module_id: str) -> Module:
    module = await session.get(Module, module_id)
    if module is None:
        raise NotFound("Module not found.")
    return module


async def _version(session: AsyncSession, version_id: str) -> ModuleVersion:
    version = await session.get(ModuleVersion, version_id)
    if version is None:
        raise NotFound("ModuleVersion not found.")
    return version


@router.get("/v1/modules")
async def list_modules(
    session: AsyncSession = Depends(get_session),
    state: str | None = Query(default=None),
) -> dict:
    query = select(Module)
    if state:
        query = query.where(Module.state == state)
    rows = (await session.execute(query.order_by(Module.created_at.desc()))).scalars().all()
    return {"modules": [module_view(module) for module in rows]}


@router.post("/v1/modules/proposals", status_code=201)
async def post_proposal(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("module_propose", device.agent_id)
    body = await request.json()
    validate_create_build_proposal(body)
    module, version, proposal = await create_build_proposal(
        session,
        agent_id=device.agent_id,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await gateway.publish(
        "community-frontier",
        "module",
        {"event": "proposed", "module_id": module.module_id, "state": module.state},
    )
    return {
        "module": module_view(module),
        "version": version_view(version),
        "proposal": proposal_view(proposal),
    }


@router.get("/v1/modules/{module_id}")
async def get_module(module_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    module = await _module(session, module_id)
    versions = (
        await session.execute(
            select(ModuleVersion)
            .where(ModuleVersion.module_id == module_id)
            .order_by(ModuleVersion.version_number)
        )
    ).scalars().all()
    proposals = (
        await session.execute(
            select(BuildProposal).where(BuildProposal.module_id == module_id)
        )
    ).scalars().all()
    return {
        **module_view(module),
        "versions": [version_view(version) for version in versions],
        "proposals": [proposal_view(proposal) for proposal in proposals],
    }


@router.post("/v1/modules/{module_id}/versions", status_code=201)
async def post_version(
    module_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_create_build_proposal(body)
    module = await _module(session, module_id)
    version = await create_module_update(
        session,
        module=module,
        agent_id=device.agent_id,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return version_view(version)


@router.post("/v1/module-versions/{version_id}/reviews", status_code=201)
async def post_review(
    version_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_review_module(body)
    version = await _version(session, version_id)
    review = await review_module_version(
        session,
        version=version,
        reviewer_agent_id=device.agent_id,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return review_view(review)


@router.post("/v1/modules/{module_id}/publish")
async def post_publish(
    module_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    module = await _module(session, module_id)
    body = await request.json() if await request.body() else {}
    module, plot, lease = await publish_module(
        session,
        module=module,
        agent_id=device.agent_id,
        plot_id=body.get("plot_id"),
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await gateway.publish(
        "community-frontier",
        "module",
        {"event": "published", "module_id": module.module_id, "plot_id": plot.plot_id},
    )
    return {
        "module": module_view(module),
        "plot": plot_view(plot),
        "lease": {
            "lease_id": lease.lease_id,
            "credits_reserved": lease.credits_reserved,
            "resource_estimate": lease.resource_estimate,
            "state": lease.state,
        },
    }


@router.post("/v1/modules/{module_id}/rollback")
async def post_rollback(
    module_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    module = await _module(session, module_id)
    module = await rollback_module(
        session,
        module=module,
        agent_id=device.agent_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return module_view(module)


@router.get("/v1/world-builder/plots")
async def list_plots(session: AsyncSession = Depends(get_session)) -> dict:
    rows = (await session.execute(select(WorldPlot).order_by(WorldPlot.slug))).scalars().all()
    return {"plots": [plot_view(plot) for plot in rows]}


@router.post("/v1/world-builder/plots/{plot_id}/runtime")
async def post_plot_runtime(
    plot_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    plot = await session.get(WorldPlot, plot_id)
    if plot is None:
        raise NotFound("WorldPlot not found.")
    body = await request.json()
    plot = await set_plot_runtime(
        session,
        plot=plot,
        runtime_state=body["runtime_state"],
        agent_id=device.agent_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return plot_view(plot)


@router.get("/v1/games")
async def list_games(session: AsyncSession = Depends(get_session)) -> dict:
    rows = (await session.execute(select(Game).order_by(Game.created_at.desc()))).scalars().all()
    return {
        "games": [
            {
                "game_id": game.game_id,
                "module_id": game.module_id,
                "name": game.name,
                "state": game.state,
                "current_version_id": game.current_version_id,
            }
            for game in rows
        ]
    }


@router.post("/v1/game-versions/{game_version_id}/sessions", status_code=201)
async def post_game_session(
    game_version_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json() if await request.body() else {}
    validate_game_session(body)
    version = await session.get(GameVersion, game_version_id)
    if version is None:
        raise NotFound("GameVersion not found.")
    game_session = await create_game_session(
        session,
        game_version=version,
        agent_id=device.agent_id,
        metadata=body.get("metadata"),
    )
    await session.commit()
    return session_view(game_session)

