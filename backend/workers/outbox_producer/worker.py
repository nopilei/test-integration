import asyncio
import logging

from backend.config import settings
from backend.services.outbox import OutboxService

logger = logging.getLogger(__name__)


class OutboxProducerWorker:
    def __init__(self, service: OutboxService) -> None:
        self._outbox_service = service
        self._poll_interval = settings.outbox_poll_interval_sec

    async def run(self) -> None:
        logger.info("[OutboxWorker] starting sending outbox events to broker")
        await self._loop()

    async def _loop(self) -> None:
        while True:
            try:
                await self._outbox_service.send_batch()
            except Exception:
                logger.exception("Outbox send_batch failed")
            await asyncio.sleep(self._poll_interval)
