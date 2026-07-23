import asyncio
import logging
import signal

from backend.config import settings
from backend.db.session import dispose_engine
from backend.logging import configure_logging
from backend.observability.checks import db_ping
from backend.observability.http_server import ProbesServer
from backend.observability.probes import ProbeRegistry
from backend.workers.reconciler.worker import ReconcilerWorker
from backend.services.monolith import FakeMonolithClient

logger = logging.getLogger(__name__)

COMPONENT = "reconciler"


async def main() -> None:
    configure_logging()
    logger.info("Starting %s", COMPONENT)

    monolith = FakeMonolithClient()
    worker = ReconcilerWorker(monolith=monolith)

    probes = ProbeRegistry()
    probes.add("db", db_ping)
    probes_server = ProbesServer(
        registry=probes, component=COMPONENT, port=settings.probes_port
    )

    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event, worker)

    await probes_server.start()
    run_task = asyncio.create_task(worker.run(), name="reconciler-loop")
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
        await probes_server.stop()
        await dispose_engine()
        logger.info("Shutdown complete")


def _install_signal_handlers(stop_event: asyncio.Event, worker: ReconcilerWorker) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(
                sig, lambda: (stop_event.set(), worker.request_stop())
            )
        except NotImplementedError:  # pragma: no cover
            pass


if __name__ == "__main__":
    asyncio.run(main())
