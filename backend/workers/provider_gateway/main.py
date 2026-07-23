import asyncio
import logging
import signal

from faststream import FastStream

from backend.config import settings
from backend.db.session import dispose_engine
from backend.logging import configure_logging
from backend.observability.checks import db_ping
from backend.observability.http_server import ProbesServer
from backend.observability.probes import ProbeRegistry
from backend.workers.provider_gateway.worker import ProviderGatewayWorker
from backend.workers.provider_gateway.client import MockProviderClient
from backend.transport.broker import create_broker, setup_topology

logger = logging.getLogger(__name__)

COMPONENT = "provider_gateway"


async def main() -> None:
    configure_logging()
    logger.info("Starting %s", COMPONENT)

    broker = create_broker()
    await broker.connect()
    await setup_topology(broker)

    provider = MockProviderClient()
    worker = ProviderGatewayWorker(broker=broker, provider=provider)

    probes = ProbeRegistry()
    probes.add("db", db_ping)
    probes.add("provider_gateway", lambda: provider.is_connected, critical=True)
    probes_server = ProbesServer(
        registry=probes, component=COMPONENT, port=settings.probes_port
    )

    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    await probes_server.start()
    await provider.start()
    await worker.start()

    app = FastStream(broker)
    app_task = asyncio.create_task(app.run(), name="faststream-app")
    stop_task = asyncio.create_task(stop_event.wait(), name="stop-event")

    try:
        _, pending = await asyncio.wait(
            {app_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
    finally:
        logger.info("Shutting down %s", COMPONENT)
        await provider.stop()
        await worker.stop()
        await broker.close()
        await probes_server.stop()
        await dispose_engine()
        logger.info("Shutdown complete")


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:  # pragma: no cover — Windows
            pass


if __name__ == "__main__":
    asyncio.run(main())
