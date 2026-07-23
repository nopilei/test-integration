import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from backend.api.errors import register_error_handlers
from backend.api.v1.router import api_router
from backend.config import settings
from backend.db.session import dispose_engine
from backend.logging import configure_logging
from backend.observability.checks import db_ping
from backend.observability.metrics import REGISTRY, process_ready, process_up
from backend.observability.probes import ProbeRegistry
from backend.services.monolith import FakeMonolithClient
from backend.transport.broker import get_broker

configure_logging()
logger = logging.getLogger(__name__)


COMPONENT = "api"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    broker = await get_broker()
    logger.info("Broker connected")
    app.state.broker = broker

    monolith = FakeMonolithClient()
    app.state.monolith = monolith

    probes = ProbeRegistry()
    probes.add("db", db_ping)
    app.state.probes = probes

    process_up.labels(component=COMPONENT).set(1)
    try:
        yield
    finally:
        logger.info("Shutting down")
        process_up.labels(component=COMPONENT).set(0)
        process_ready.labels(component=COMPONENT).set(0)
        await monolith.close()
        await broker.close()
        await dispose_engine()
        logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        default_response_class=JSONResponse,
    )
    register_error_handlers(app)
    app.include_router(api_router)

    @app.get("/health/live", tags=["system"])
    async def health_live() -> dict[str, str]:
        probes: ProbeRegistry = app.state.probes
        if probes.is_alive():
            return {"status": "alive"}
        return JSONResponse({"status": "dead"}, status_code=503)

    @app.get("/health/ready", tags=["system"])
    async def health_ready() -> Response:
        probes: ProbeRegistry = app.state.probes
        ok = await probes.is_ready()
        process_ready.labels(component=COMPONENT).set(1 if ok else 0)
        if ok:
            return JSONResponse({"status": "ready"})
        return JSONResponse(
            {
                "status": "not_ready",
                "checks": {p.name: p.last_ok for p in probes.probes},
            },
            status_code=503,
        )

    @app.get("/health/startup", tags=["system"])
    async def health_startup() -> Response:
        probes: ProbeRegistry = app.state.probes
        ok = await probes.has_started()
        if ok:
            return JSONResponse({"status": "started"})
        return JSONResponse(
            {
                "status": "starting",
                "checks": {p.name: p.succeeded_once for p in probes.probes},
            },
            status_code=503,
        )

    @app.get("/health", tags=["system"], include_in_schema=False)
    async def health_legacy() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics", tags=["system"])
    async def metrics() -> Response:
        return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
