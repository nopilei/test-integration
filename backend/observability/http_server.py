import logging

from aiohttp import web
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from backend.observability.metrics import REGISTRY, process_ready, process_up
from backend.observability.probes import ProbeRegistry

logger = logging.getLogger(__name__)


class ProbesServer:
    def __init__(
        self,
        registry: ProbeRegistry,
        component: str,
        port: int,
        host: str = "0.0.0.0",
    ) -> None:
        self._probes = registry
        self._component = component
        self._host = host
        self._port = port
        self._runner: web.AppRunner | None = None
        process_up.labels(component=component).set(0)
        process_ready.labels(component=component).set(0)

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/health/live", self._live)
        app.router.add_get("/health/ready", self._ready)
        app.router.add_get("/health/startup", self._startup)
        app.router.add_get("/metrics", self._metrics)
        self._runner = web.AppRunner(app, handle_signals=False)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        process_up.labels(component=self._component).set(1)
        logger.info(
            "Probes server started on %s:%s (component=%s)",
            self._host, self._port, self._component,
        )

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
        process_up.labels(component=self._component).set(0)
        process_ready.labels(component=self._component).set(0)
        logger.info("Probes server stopped (component=%s)", self._component)

    async def _live(self, request: web.Request) -> web.Response:
        if self._probes.is_alive():
            return web.json_response({"status": "alive"})
        return web.json_response({"status": "dead"}, status=503)

    async def _ready(self, request: web.Request) -> web.Response:
        ok = await self._probes.is_ready()
        process_ready.labels(component=self._component).set(1 if ok else 0)
        if ok:
            return web.json_response({"status": "ready"})
        return web.json_response(
            {
                "status": "not_ready",
                "checks": {p.name: p.last_ok for p in self._probes.probes},
            },
            status=503,
        )

    async def _startup(self, request: web.Request) -> web.Response:
        ok = await self._probes.has_started()
        if ok:
            return web.json_response({"status": "started"})
        return web.json_response(
            {
                "status": "starting",
                "checks": {p.name: p.succeeded_once for p in self._probes.probes},
            },
            status=503,
        )

    async def _metrics(self, request: web.Request) -> web.Response:
        payload = generate_latest(REGISTRY)
        return web.Response(body=payload, content_type=CONTENT_TYPE_LATEST)
