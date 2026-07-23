import logging

from faststream import FastStream
from faststream.rabbit import RabbitBroker

from backend.constants import ProviderMessageType
from backend.db.session import session_scope
from backend.workers.provider_gateway.schemas import (
    CancellationAppliedPayload,
    Message,
    RecommendationPayload,
)
from backend.services.monolith import FakeMonolithClient
from backend.services.ticket import TicketService
from backend.transport.broker import (
    CONSUMER_ACK_POLICY,
    provider_in_queue,
    tickets_exchange,
)

logger = logging.getLogger(__name__)


class ProviderConsumerWorker:
    """Читает сообщения от провайдера через RabbitMQ и стучится в монолит."""

    def __init__(
        self,
        broker: RabbitBroker,
        monolith: FakeMonolithClient,
    ) -> None:
        self._broker = broker
        self._monolith = monolith
        self._app = FastStream(broker)
        broker.subscriber(
            provider_in_queue,
            exchange=tickets_exchange,
            ack_policy=CONSUMER_ACK_POLICY,
        )(self._handle)

    async def run_loop(self) -> None:
        await self._app.run()

    async def _handle(self, payload: dict) -> None:
        message = Message.model_validate(payload)
        logger.info(
            "inbound frame type=%s message_id=%s ticket=%s",
            message.type.value, message.message_id, message.ticket_id,
        )

        if message.type is ProviderMessageType.RECOMMENDATION:
            recommendation = RecommendationPayload.model_validate(message.payload)
            async with session_scope() as session:
                service = TicketService(session=session, monolith=self._monolith)
                await service.apply_recommendation(recommendation)
            return

        if message.type is ProviderMessageType.CANCELLATION_APPLIED:
            cancellation = CancellationAppliedPayload.model_validate(message.payload)
            async with session_scope() as session:
                service = TicketService(session=session, monolith=self._monolith)
                await service.mark_cancellation_applied(cancellation.ticket_id)
            return

        logger.info(
            "ignoring inbound frame of type %s (no handler)",
            message.type.value,
        )
