import logging
import uuid

from faststream.rabbit import RabbitBroker

from backend.config import settings
from backend.db.repositories.outbox import OutboxRepository
from backend.db.session import session_scope
from backend.transport.broker import tickets_exchange

logger = logging.getLogger(__name__)


class OutboxService:
    """Опрашивает таблицу Outbox и пишет в очередь."""

    def __init__(self, broker: RabbitBroker, batch_size: int = settings.outbox_batch_size) -> None:
        self._broker = broker
        self._batch_size = batch_size

    async def send_batch(self) -> int:
        async with session_scope() as session:
            repo = OutboxRepository(session)
            pending = await repo.fetch_pending(limit=self._batch_size)
            if not pending:
                return 0

            published_ids: list[uuid.UUID] = []
            failed: list[tuple[uuid.UUID, str]] = []
            for event in pending:
                try:
                    await self._broker.publish(
                        message=event.payload,
                        exchange=tickets_exchange,
                        routing_key=event.routing_key,
                        headers={
                            "event_id": str(event.id),
                            "event_type": event.event_type,
                        },
                        message_id=str(event.id),
                        persist=True,
                    )
                    published_ids.append(event.id)
                except Exception as exc:
                    logger.exception(
                        "Failed to publish outbox event %s.",
                        event.id,
                    )
                    failed.append((event.id, str(exc)))

            await repo.mark_published_many(published_ids)
            for event_id, err in failed:
                await repo.mark_failed(event_id, err)
            await session.commit()

            if published_ids:
                logger.info(
                    "Published %s outbox events, %s failed",
                    len(published_ids),
                    len(failed),
                )
            return len(published_ids)
