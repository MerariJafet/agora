from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from agora_api import __version__
from agora_api.config import get_settings
from agora_api.db import dispose_engine
from agora_api.errors import AgoraError, agora_error_handler, validation_error_handler
from agora_api.logging import configure_logging, get_logger
from agora_api.middleware import RequestContextMiddleware
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
    health,
    knowledge,
    magna,
    magna_knowledge,
    magna_private_pilot,
    magna_tokoin,
    mission_challenges,
    missions,
    modules,
    owner,
    passports,
    realtime,
    registration,
    research_market,
    spaces,
    stabilization,
    tokoins,
    world,
    world_actionability,
    world_market,
    world_opportunities,
)

log = get_logger("agora.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
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
    try:
        await gateway.start()
        gateway_started = True
    except Exception as exc:
        if settings.is_production:
            raise
        log.warning("realtime.gateway_unavailable_dev", error=str(exc))
    yield
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
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
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
    app.include_router(agents.router)
    app.include_router(devices.router)
    app.include_router(enrollment.router)
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
    app.include_router(magna_private_pilot.router)
    app.include_router(research_market.router)
    app.include_router(agent_self.router)
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
