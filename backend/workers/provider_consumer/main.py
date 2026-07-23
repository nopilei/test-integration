import asyncio
import logging
import signal

from backend.config import settings
from backend.db.session import dispose_engine
from backend.logging import configure_logging
from backend.observability.checks import db_ping
from backend.observability.http_server import ProbesServer
from backend.observability.probes import ProbeRegistry
from backend.workers.provider_consumer.worker import ProviderConsumerWorker
from backend.services.monolith import FakeMonolithClient
from backend.transport.broker import create_broker, setup_topology

logger = logging.getLogger(__name__)

COMPONENT = "provider_consumer"


async def main() -> None:
    configure_logging()
    logger.info("Starting %s", COMPONENT)

    broker = create_broker()
    await broker.connect()
    await setup_topology(broker)

    monolith = FakeMonolithClient()
    worker = ProviderConsumerWorker(broker=broker, monolith=monolith)

    probes = ProbeRegistry()
    probes.add("db", db_ping)
    probes_server = ProbesServer(
        registry=probes, component=COMPONENT, port=settings.probes_port
    )

    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    await probes_server.start()

    run_task = asyncio.create_task(worker.run_loop(), name="provider-consumer")
    stop_task = asyncio.create_task(stop_event.wait(), name="stop-event")

    try:
        _, pending = await asyncio.wait(
            {run_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
    finally:
        logger.info("Shutting down %s", COMPONENT)
        await monolith.close()
        await broker.close()
        await probes_server.stop()
        await dispose_engine()
        logger.info("Shutdown complete")


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:  # pragma: no cover
            pass


if __name__ == "__main__":
    asyncio.run(main())
