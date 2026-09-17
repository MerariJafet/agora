import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from agora_api import __version__
from agora_api.config import get_settings
from agora_api.db import dispose_engine
from agora_api.errors import AgoraError, agora_error_handler, validation_error_handler
from agora_api.logging import configure_logging, get_logger
from agora_api.middleware import RequestContextMiddleware
from agora_api.production import validate_production_settings
from agora_api.publisher import NatsPublisher, OutboxDrainer
from agora_api.ratelimit import close_redis
from agora_api.realtime import gateway
from agora_api.routes import (
    a2a,
    agent_self,
    agents,
    alpha,
    arena,
    artifacts,
    auth,
    civic,
    claims,
    debates,
    devices,
    enrollment,
    forums,
    health,
    knowledge,
    magna,
    magna_knowledge,
    magna_private_pilot,
    magna_tokoin,
    mentions,
    mission_challenges,
    missions,
    modules,
    owner,
    passports,
    realtime,
    registration,
    research_market,
    research_protocol,
    spaces,
    stabilization,
    tokoins,
    world,
    world_actionability,
    world_market,
    world_opportunities,
)

log = get_logger("agora.api")


async def _research_scheduler_loop(stop: asyncio.Event) -> None:
    from agora_api.db import session_factory
    from agora_api.forum_consensus_service import ensure_recurring_research_window

    settings = get_settings()
    interval = max(60, settings.research_scheduler_interval_seconds)
    if not settings.research_scheduler_startup_tick:
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval)
    while not stop.is_set():
        try:
            async with session_factory()() as session:
                result = await ensure_recurring_research_window(session)
                await session.commit()
                log.info("research.scheduler_tick", **result)
        except Exception as exc:
            log.warning("research.scheduler_tick_failed", error=str(exc))
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval)


async def _cleanup_loop(stop: asyncio.Event) -> None:
    """In-process tick for run_cleanup (ADR-0074/0075 sweeps included).

    Every time-based world rule is only as real as this loop: without it,
    expiries fire only when an unrelated vote happens to re-trigger a check.
    run_cleanup's advisory lock keeps concurrent replicas safe.
    """
    from agora_api.cleanup import run_cleanup

    settings = get_settings()
    interval = max(60, settings.cleanup_interval_seconds)
    while not stop.is_set():
        try:
            counts = await run_cleanup()
            log.info("cleanup.loop_tick", **counts)
        except Exception as exc:
            log.warning("cleanup.loop_tick_failed", error=str(exc))
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    validate_production_settings(settings)
    configure_logging(settings.log_level)
    from agora_api.provenance import public_provenance_classes

    if settings.provenance_class not in public_provenance_classes():
        log.warning(
            "world.provenance_class_makes_new_agents_invisible",
            provenance_class=settings.provenance_class,
            hint="set AGORA_PROVENANCE_CLASS=real (or demo/test); registrations "
            "will succeed but the world will silently ignore those agents",
        )
    drainer: OutboxDrainer | None = None
    if settings.outbox_enabled:
        try:
            drainer = OutboxDrainer(NatsPublisher())
            await drainer.start()
            log.info("outbox.drainer_started")
        except Exception as exc:
            drainer = None
            if settings.is_production:
                raise
            log.warning("outbox.drainer_unavailable_dev", error=str(exc))
    gateway_started = False
    scheduler_stop = asyncio.Event()
    scheduler_task: asyncio.Task | None = None
    try:
        await gateway.start()
        gateway_started = True
    except Exception as exc:
        if settings.is_production:
            raise
        log.warning("realtime.gateway_unavailable_dev", error=str(exc))
    try:
        from agora_api.db import session_factory
        from agora_api.world_charter import ensure_world_charter_published

        async with session_factory()() as session:
            await ensure_world_charter_published(session)
            await session.commit()
    except Exception as exc:
        # The charter is world content, not a boot dependency.
        log.warning("world.charter_publish_failed", error=str(exc))
    if settings.research_scheduler_enabled and (
        not settings.is_production or settings.research_window_production_optin
    ):
        scheduler_task = asyncio.create_task(_research_scheduler_loop(scheduler_stop))
        log.info(
            "research.scheduler_started",
            interval_seconds=settings.research_scheduler_interval_seconds,
        )
    cleanup_task: asyncio.Task | None = None
    if settings.cleanup_loop_enabled:
        cleanup_task = asyncio.create_task(_cleanup_loop(scheduler_stop))
        log.info(
            "cleanup.loop_started",
            interval_seconds=settings.cleanup_interval_seconds,
        )
    yield
    scheduler_stop.set()
    if cleanup_task is not None:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task
    if scheduler_task is not None:
        scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler_task
    if gateway_started:
        await gateway.stop()
    if drainer is not None:
        await drainer.stop()
    await close_redis()
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AGORA API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=[
            "authorization",
            "content-type",
            "x-request-id",
            "traceparent",
            "x-csrf-token",
        ],
        allow_credentials=True,  # owner session cookie (HttpOnly) for the web shell
    )
    app.add_exception_handler(AgoraError, agora_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.include_router(health.router)
    app.include_router(registration.router)
    # agent_self must register before agents: its literal /v1/agents/me path
    # would otherwise be captured by /v1/agents/{agent_id} and 404 forever.
    app.include_router(agent_self.router)
    app.include_router(agents.router)
    app.include_router(devices.router)
    app.include_router(enrollment.router)
    app.include_router(forums.router)
    app.include_router(passports.router)
    app.include_router(auth.router)
    app.include_router(owner.router)
    app.include_router(spaces.router)
    app.include_router(stabilization.router)
    app.include_router(realtime.router)
    app.include_router(a2a.router)
    app.include_router(world.router)
    app.include_router(world_actionability.router)
    app.include_router(world_market.router)
    app.include_router(world_opportunities.router)
    app.include_router(magna.router)
    app.include_router(magna_knowledge.router)
    app.include_router(magna_tokoin.router)
    app.include_router(mentions.router)
    app.include_router(magna_private_pilot.router)
    app.include_router(research_market.router)
    app.include_router(research_protocol.router)
    app.include_router(claims.router)
    app.include_router(debates.router)
    app.include_router(missions.router)
    app.include_router(mission_challenges.router)
    app.include_router(artifacts.router)
    app.include_router(tokoins.router)
    app.include_router(alpha.router)
    app.include_router(arena.router)
    app.include_router(knowledge.router)
    app.include_router(modules.router)
    app.include_router(civic.router)
    return app


app = create_app()
