import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from backend.config import settings
from backend.constants import Currency, ProviderMessageType, RecommendationAction, TicketStatus
from backend.db.models.ticket import Ticket
from backend.services.ticket import TicketService
from backend.workers.provider_gateway.client import MockProviderClient
from backend.workers.provider_gateway.schemas import (
    Message,
    ProviderAckError,
    Selection,
    TicketPayload,
)


def _ticket() -> Ticket:
    return Ticket(
        id=uuid.uuid4(),
        idempotency_key="test-key",
        user_id=uuid.uuid4(),
        stake_amount=Decimal("50.00"),
        currency=Currency.RUB,
        selections=[{"event_id": "match:1", "market": "1x2", "odds": "2.0"}],
        status=TicketStatus.NEW,
    )


def test_build_ticket_and_ack_messages():
    ticket = _ticket()
    outbound = TicketService._build_ticket_message(ticket)
    assert outbound.type is ProviderMessageType.TICKET
    assert outbound.ticket_id == ticket.id
    assert outbound.payload["currency"] == "RUB"

    confirm = TicketService._build_ack_message(ticket, RecommendationAction.ACCEPT)
    assert confirm.type is ProviderMessageType.CONFIRM_RECOMMENDATION

    decline = TicketService._build_ack_message(ticket, RecommendationAction.DECLINE)
    assert decline.type is ProviderMessageType.DECLINE_RECOMMENDATION


@pytest.mark.asyncio
async def test_mock_provider_send_ok_and_ack_error(monkeypatch):
    monkeypatch.setattr(settings, "provider_mock_min_delay_sec", 0.0)
    monkeypatch.setattr(settings, "provider_mock_max_delay_sec", 0.0)
    monkeypatch.setattr(settings, "provider_mock_transport_error_rate", 0.0)
    monkeypatch.setattr(settings, "provider_mock_ack_error_rate", 0.0)

    client = MockProviderClient()
    await client.start()
    message = Message.build(
        TicketPayload(
            ticket_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            stake_amount=Decimal("10"),
            currency="RUB",
            selections=[Selection(event_id="e", market="1x2", odds=Decimal("1.5"))],
            placed_at=datetime.now(tz=UTC),
        ),
        type=ProviderMessageType.TICKET,
        ticket_id=uuid.uuid4(),
    )

    ack = await client.send(message)
    assert ack.status == "ok"
    assert ack.ack_of == message.message_id

    monkeypatch.setattr(settings, "provider_mock_ack_error_rate", 1.0)
    with pytest.raises(ProviderAckError) as exc_info:
        await client.send(message)
    assert exc_info.value.ack.status == "error"

    await client.stop()
