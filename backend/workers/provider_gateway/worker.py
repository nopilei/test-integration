import asyncio
import logging
from datetime import UTC, datetime

from faststream.rabbit import RabbitBroker

from backend.constants import (
    ProviderMessageType,
    TERMINAL_TICKET_STATUSES,
    TicketStatus,
)
from backend.db.repositories.ticket import TicketRepository
from backend.db.session import session_scope
from backend.observability.metrics import ticket_state_transition_total
from backend.transport.broker import (
    CONSUMER_ACK_POLICY,
    provider_out_queue,
    tickets_exchange,
)
from backend.transport.topology import TOPOLOGY
from backend.workers.provider_gateway.client import ProviderClient
from backend.workers.provider_gateway.schemas import Message, ProviderAckError

logger = logging.getLogger(__name__)


class ProviderGatewayWorker:
    """Коммуникация RabbitMQ <-> Provider."""

    def __init__(self, broker: RabbitBroker, provider: ProviderClient) -> None:
        self._broker = broker
        self._provider = provider
        self._recieve_from_provider_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._recieve_from_provider_task = asyncio.create_task(self._recieve_from_provider())
        self._broker.subscriber(
            provider_out_queue,
            exchange=tickets_exchange,
            ack_policy=CONSUMER_ACK_POLICY,
        )(self._send_to_provider)

    async def stop(self) -> None:
        if self._recieve_from_provider_task is None:
            return
        self._recieve_from_provider_task.cancel()
        try:
            await self._recieve_from_provider_task
        except asyncio.CancelledError:
            pass

    async def _send_to_provider(self, payload: dict) -> None:
        message = Message.model_validate(payload)
        logger.info(
            "outbound frame type=%s message_id=%s ticket=%s",
            message.type.value, message.message_id, message.ticket_id,
        )
        try:
            await self._provider.send(message)
        except ProviderAckError as exc:
            logger.error(
                "provider rejected frame type=%s ticket=%s: %s",
                message.type.value, message.ticket_id, exc,
            )
            await self._handle_message_rejection(message, exc)
            return

        await self._handle_message_success_ack(message)

    async def _recieve_from_provider(self) -> None:
        async for message in self._provider:
            try:
                await self._broker.publish(
                    message=message.model_dump(mode="json"),
                    exchange=tickets_exchange,
                    routing_key=TOPOLOGY.provider_in_routing_key,
                    headers={
                        "provider_message_id": str(message.message_id),
                        "provider_message_type": message.type.value,
                    },
                    message_id=str(message.message_id),
                    persist=True,
                )
            except Exception:
                logger.exception(
                    "Failed to persist inbound frame message_id=%s — NOT acking provider",
                    message.message_id,
                )
                return

            try:
                await self._provider.send_ack(message.message_id)
            except Exception:
                logger.exception("Failed to ack inbound message_id=%s", message.message_id)

    async def _handle_message_success_ack(self, message: Message) -> None:
        if message.ticket_id is None:
            return

        target: TicketStatus | None
        if message.type is ProviderMessageType.TICKET:
            target = TicketStatus.SENT_TO_PROVIDER
        elif message.type is ProviderMessageType.CONFIRM_RECOMMENDATION:
            target = TicketStatus.CONFIRMED
        elif message.type is ProviderMessageType.DECLINE_RECOMMENDATION:
            target = TicketStatus.DECLINED
        elif message.type is ProviderMessageType.REQUEST_CANCELLATION:
            return
        else:
            return

        async with session_scope() as session:
            repo = TicketRepository(session)
            ticket = await repo.get_by_id_for_update(message.ticket_id)
            if ticket is None or ticket.status in TERMINAL_TICKET_STATUSES:
                return
            if target is TicketStatus.SENT_TO_PROVIDER and ticket.status != TicketStatus.NEW:
                return
            previous = ticket.status
            ticket.status = target
            if target in (TicketStatus.CONFIRMED, TicketStatus.DECLINED):
                ticket.confirmed_at = ticket.confirmed_at or datetime.now(tz=UTC)
            await session.commit()
        ticket_state_transition_total.labels(from_status=previous.value, to_status=target.value).inc()

    async def _handle_message_rejection(
        self, message: Message, exc: ProviderAckError
    ) -> None:
        pass
