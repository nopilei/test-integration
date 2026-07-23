import asyncio
import logging
import random
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from backend.config import settings
from backend.constants import ProviderMessageType, RecommendationAction
from backend.workers.provider_gateway.schemas import (
    AckPayload,
    CancellationAppliedPayload,
    Message,
    ProviderAckError,
    ProviderErrorCode,
    RecommendationPayload,
)

logger = logging.getLogger(__name__)

_CLOSED = object()


class ProviderClient(ABC):
    """Вебсокет клиент к провайдеру."""

    @abstractmethod
    async def start(self) -> None:
        pass

    @abstractmethod
    async def stop(self) -> None:
        pass

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        pass

    @abstractmethod
    async def send(self, message: Message) -> AckPayload:
        pass

    @abstractmethod
    async def send_ack(self, message_id: uuid.UUID) -> None:
        pass

    @abstractmethod
    def __aiter__(self) -> AsyncIterator[Message]:
        pass

    @abstractmethod
    async def __anext__(self) -> Message:
        pass


class MockProviderClient(ProviderClient):
    """Симуляция двусторонней вебсокет сессии с провайдером."""

    def __init__(self) -> None:
        self._inbound: asyncio.Queue[Message | object] = asyncio.Queue()
        self._background_tasks: set[asyncio.Task] = set()
        self._connected = False

    async def start(self) -> None:
        self._connected = True
        logger.info("mock provider channel started")

    async def stop(self) -> None:
        self._connected = False
        for task in list(self._background_tasks):
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        await self._inbound.put(_CLOSED)

    @property
    def is_connected(self) -> bool:
        return self._connected

    def __aiter__(self) -> AsyncIterator[Message]:
        return self

    async def __anext__(self) -> Message:
        item = await self._inbound.get()
        if item is _CLOSED:
            raise StopAsyncIteration
        return item

    async def send(self, message: Message) -> AckPayload:
        await asyncio.sleep(
            random.uniform(settings.provider_mock_min_delay_sec, settings.provider_mock_max_delay_sec)
        )

        roll = random.random()
        if roll < settings.provider_mock_transport_error_rate:
            raise ConnectionError("mock provider: simulated transport failure")

        if roll < settings.provider_mock_transport_error_rate + settings.provider_mock_ack_error_rate:
            error_code = random.choice(list(ProviderErrorCode))
            raise ProviderAckError(
                AckPayload(ack_of=message.message_id, status="error", error_code=error_code)
            )

        self._schedule_response(message)
        return AckPayload(ack_of=message.message_id, status="ok")

    async def send_ack(self, message_id: uuid.UUID) -> None:
        logger.debug("mock provider: ack_inbound message_id=%s", message_id)

    def _schedule_response(self, message: Message) -> None:
        if message.ticket_id is None:
            return
        if message.type is ProviderMessageType.TICKET:
            coro = self._push_recommendation(message.ticket_id)
        elif message.type is ProviderMessageType.REQUEST_CANCELLATION:
            coro = self._push_cancellation_applied(message.ticket_id)
        else:
            return
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _push_recommendation(self, ticket_id: uuid.UUID) -> None:
        await asyncio.sleep(
            random.uniform(
                settings.provider_mock_recommendation_min_delay_sec,
                settings.provider_mock_recommendation_max_delay_sec,
            )
        )
        action = (
            RecommendationAction.ACCEPT
            if random.random() < settings.provider_mock_accept_probability
            else RecommendationAction.DECLINE
        )
        payload = RecommendationPayload(
            ticket_id=ticket_id,
            action=action,
            reason="mock risk engine decision",
            expires_at=datetime.now(tz=UTC) + timedelta(seconds=settings.ticket_recommendation_timeout_sec),
        )
        await self._deliver_message_from_provider(
            Message.build(payload, type=ProviderMessageType.RECOMMENDATION, ticket_id=ticket_id)
        )

    async def _push_cancellation_applied(self, ticket_id: uuid.UUID) -> None:
        await asyncio.sleep(random.uniform(0.05, 0.3))
        payload = CancellationAppliedPayload(ticket_id=ticket_id)
        await self._deliver_message_from_provider(
            Message.build(payload, type=ProviderMessageType.CANCELLATION_APPLIED, ticket_id=ticket_id)
        )

    async def _deliver_message_from_provider(self, message: Message) -> None:
        await self._inbound.put(message)
