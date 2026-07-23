import asyncio
import logging

from backend.logging import configure_logging
from backend.workers.outbox_producer.worker import OutboxProducerWorker
from backend.services.outbox import OutboxService
from backend.transport.broker import create_broker, setup_topology

logger = logging.getLogger(__name__)


async def main() -> None:
    configure_logging()
    logger.info("Starting outbox producer")

    broker = create_broker()
    async with broker:
        await setup_topology(broker)
        service = OutboxService(broker=broker)
        worker = OutboxProducerWorker(service=service)
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
