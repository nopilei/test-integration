import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.constants import (
    EVENT_TYPE_TICKET_OUTBOUND,
    Currency,
    ProviderMessageType,
    RecommendationAction,
    TERMINAL_TICKET_STATUSES,
    TicketStatus,
)
from backend.db.models.ticket import Ticket
from backend.db.repositories.outbox import OutboxRepository
from backend.db.repositories.ticket import TicketRepository
from backend.observability.metrics import (
    ticket_state_transition_total,
    tickets_created_total,
)
from backend.workers.provider_gateway.schemas import (
    ConfirmRecommendationPayload,
    DeclineRecommendationPayload,
    Message,
    RecommendationPayload,
    RequestCancellationPayload,
    Selection,
    TicketPayload,
)
from backend.services.monolith import (
    FakeMonolithClient,
    MonolithError,
)
from backend.transport.topology import TOPOLOGY

logger = logging.getLogger(__name__)


@dataclass
class CreateTicketRequest:
    user_id: uuid.UUID
    stake_amount: Decimal
    currency: str
    selections: list[dict[str, Any]]


@dataclass
class CreateTicketResult:
    ticket: Ticket
    created: bool


class TicketService:
    """Логика обработки тикета."""

    def __init__(
        self,
        session: AsyncSession,
        monolith: FakeMonolithClient,
    ) -> None:
        self._session = session
        self._ticket_repo = TicketRepository(session)
        self._outbox_repo = OutboxRepository(session)
        self._monolith_client = monolith

    async def create_ticket(
        self,
        idempotency_key: str,
        request: CreateTicketRequest,
    ) -> CreateTicketResult:
        existing = await self._ticket_repo.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            return CreateTicketResult(ticket=existing, created=False)

        ticket = Ticket(
            id=uuid.uuid4(),
            idempotency_key=idempotency_key,
            user_id=request.user_id,
            stake_amount=request.stake_amount,
            currency=Currency(request.currency),
            selections=request.selections,
            status=TicketStatus.NEW,
        )

        try:
            await self._ticket_repo.add(ticket)
            message = self._build_ticket_message(ticket)
            await self._outbox_repo.add(
                entity_id=ticket.id,
                event_type=EVENT_TYPE_TICKET_OUTBOUND,
                routing_key=TOPOLOGY.provider_out_routing_key,
                payload=message.model_dump(mode="json"),
            )
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            existing = await self._ticket_repo.get_by_idempotency_key(idempotency_key)
            if existing is None:
                raise
            return CreateTicketResult(ticket=existing, created=False)

        tickets_created_total.labels(
            currency=ticket.currency.value if isinstance(ticket.currency, Currency) else ticket.currency
        ).inc()
        return CreateTicketResult(ticket=ticket, created=True)

    async def get_ticket(self, ticket_id: uuid.UUID) -> Ticket | None:
        return await self._ticket_repo.get_by_id(ticket_id)

    async def apply_recommendation(self, payload: RecommendationPayload) -> None:
        ticket = await self._ticket_repo.get_by_id_for_update(payload.ticket_id)
        if ticket is None:
            logger.warning("Recommendation for unknown ticket %s", payload.ticket_id)
            return

        if ticket.status in TERMINAL_TICKET_STATUSES:
            logger.info(
                "Ignoring recommendation for terminal ticket %s (status=%s)",
                ticket.id, ticket.status.value,
            )
            return

        target = (
            TicketStatus.RECOMMENDED_CONFIRM
            if payload.action == RecommendationAction.ACCEPT
            else TicketStatus.RECOMMENDED_DECLINE
        )
        ticket.provider_recommendation = payload.action
        ticket.provider_reason = payload.reason
        ticket.provider_recommendation_at = datetime.now(tz=UTC)
        await self._change_status(ticket, to=target, commit=False)
        await self._session.commit()

        try:
            await self._monolith_client.process_ticket(
                ticket.id,
                action=payload.action,
                provider_reason=payload.reason,
            )
        except MonolithError as exc:
            logger.warning(
                "Monolith failure for ticket %s: %s — requesting cancellation",
                ticket.id, exc,
            )
            await self.request_cancellation(ticket.id, reason=f"monolith_error: {exc}")
            return

        ticket = await self._ticket_repo.get_by_id_for_update(ticket.id)
        if ticket is None or ticket.status in TERMINAL_TICKET_STATUSES:
            await self._session.commit()
            return
        ticket.settled_at = datetime.now(tz=UTC)
        await self._change_status(ticket, to=TicketStatus.SETTLED, commit=False)
        message = self._build_ack_message(ticket, action=payload.action)
        await self._outbox_repo.add(
            entity_id=ticket.id,
            event_type=EVENT_TYPE_TICKET_OUTBOUND,
            routing_key=TOPOLOGY.provider_out_routing_key,
            payload=message.model_dump(mode="json"),
        )
        await self._session.commit()

    async def mark_provider_ack_delivered(
        self,
        ticket_id: uuid.UUID,
        action: RecommendationAction,
    ) -> None:
        ticket = await self._ticket_repo.get_by_id_for_update(ticket_id)
        if ticket is None or ticket.status in TERMINAL_TICKET_STATUSES:
            logger.warning("Ticket %s not found or already in final state", ticket_id)
            return
        target = (
            TicketStatus.CONFIRMED
            if action == RecommendationAction.ACCEPT
            else TicketStatus.DECLINED
        )
        ticket.confirmed_at = datetime.now(tz=UTC)
        await self._change_status(ticket, to=target, commit=False)
        await self._session.commit()

    async def request_cancellation(
        self,
        ticket_id: uuid.UUID,
        reason: str,
    ) -> None:
        """Положить в очередь сообщение REQUEST_CANCELLATION для провайдера и обновить статус тикета."""
        ticket = await self._ticket_repo.get_by_id_for_update(ticket_id)
        if ticket is None:
            logger.warning("Ticket %s not found", ticket_id)
            return

        try:
            await self._monolith_client.process_ticket(ticket.id)
        except MonolithError:
            logger.exception("Cancel call to monolith failed for %s", ticket.id)

        ticket.failure_reason = (reason or "")[:1024]
        ticket.cancelled_at = datetime.now(tz=UTC)
        await self._change_status(
            ticket, to=TicketStatus.CANCELLATION_REQUESTED, commit=False
        )
        message = Message.build(
            RequestCancellationPayload(ticket_id=ticket.id, reason=reason),
            type=ProviderMessageType.REQUEST_CANCELLATION,
            ticket_id=ticket.id,
        )
        await self._outbox_repo.add(
            entity_id=ticket.id,
            event_type=EVENT_TYPE_TICKET_OUTBOUND,
            routing_key=TOPOLOGY.provider_out_routing_key,
            payload=message.model_dump(mode="json"),
        )
        await self._session.commit()

    async def mark_cancellation_applied(self, ticket_id: uuid.UUID) -> None:
        """Провайдер подтвердил наш запрос на REQUEST_CANCELLATION, меняем стутус."""
        ticket = await self._ticket_repo.get_by_id_for_update(ticket_id)
        if ticket is None or ticket.status == TicketStatus.CANCELLED:
            return
        ticket.cancelled_at = ticket.cancelled_at or datetime.now(tz=UTC)
        await self._change_status(ticket, to=TicketStatus.CANCELLED, commit=False)
        await self._session.commit()

    async def _change_status(
        self,
        ticket: Ticket,
        to: TicketStatus,
        commit: bool,
    ) -> None:
        from_status = ticket.status
        if from_status == to:
            return
        ticket.status = to
        ticket_state_transition_total.labels(
            from_status=from_status.value, to_status=to.value
        ).inc()
        logger.info(
            "ticket %s transition %s -> %s",
            ticket.id, from_status.value, to.value,
        )
        await self._session.flush()
        if commit:
            await self._session.commit()

    @staticmethod
    def _build_ticket_message(ticket: Ticket) -> Message:
        payload = TicketPayload(
            ticket_id=ticket.id,
            user_id=ticket.user_id,
            stake_amount=ticket.stake_amount,
            currency=ticket.currency,
            selections=[Selection(**s) for s in ticket.selections],
            placed_at=datetime.now(tz=UTC),
        )
        return Message.build(
            payload,
            type=ProviderMessageType.TICKET,
            ticket_id=ticket.id,
        )

    @staticmethod
    def _build_ack_message(ticket: Ticket, action: RecommendationAction) -> Message:
        if action == RecommendationAction.ACCEPT:
            return Message.build(
                ConfirmRecommendationPayload(ticket_id=ticket.id),
                type=ProviderMessageType.CONFIRM_RECOMMENDATION,
                ticket_id=ticket.id,
            )
        return Message.build(
            DeclineRecommendationPayload(ticket_id=ticket.id),
            type=ProviderMessageType.DECLINE_RECOMMENDATION,
            ticket_id=ticket.id,
        )
