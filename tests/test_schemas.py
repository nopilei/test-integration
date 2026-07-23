import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from backend.constants import (
    ProviderMessageType,
    RecommendationAction,
    TERMINAL_TICKET_STATUSES,
    TicketStatus,
)
from backend.workers.provider_gateway.schemas import (
    AckPayload,
    Message,
    ProviderErrorCode,
    RecommendationPayload,
    TicketPayload,
    Selection,
)


def test_terminal_statuses():
    assert TicketStatus.CONFIRMED in TERMINAL_TICKET_STATUSES
    assert TicketStatus.NEW not in TERMINAL_TICKET_STATUSES
    assert TicketStatus.SENT_TO_PROVIDER not in TERMINAL_TICKET_STATUSES


def test_message_build_and_roundtrip():
    ticket_id = uuid.uuid4()
    payload = TicketPayload(
        ticket_id=ticket_id,
        user_id=uuid.uuid4(),
        stake_amount=Decimal("100.00"),
        currency="RUB",
        selections=[Selection(event_id="e1", market="1x2", odds=Decimal("1.85"))],
        placed_at=datetime.now(tz=UTC),
    )
    message = Message.build(
        payload,
        type=ProviderMessageType.TICKET,
        ticket_id=ticket_id,
    )

    restored = Message.model_validate(message.model_dump(mode="json"))
    assert restored.type is ProviderMessageType.TICKET
    assert restored.ticket_id == ticket_id
    assert restored.payload["currency"] == "RUB"
    assert restored.payload["selections"][0]["event_id"] == "e1"


def test_ack_payload_accepts_error_code_enum():
    ack = AckPayload(
        ack_of=uuid.uuid4(),
        status="error",
        error_code=ProviderErrorCode.TICKET_EXPIRED,
    )
    assert ack.error_code is ProviderErrorCode.TICKET_EXPIRED
    dumped = ack.model_dump(mode="json")
    assert dumped["error_code"] == "ticket_expired"


def test_recommendation_payload_validation():
    payload = RecommendationPayload(
        ticket_id=uuid.uuid4(),
        action=RecommendationAction.ACCEPT,
        reason="ok",
        expires_at=datetime.now(tz=UTC) + timedelta(seconds=30),
    )
    assert payload.action is RecommendationAction.ACCEPT

    with pytest.raises(Exception):
        RecommendationPayload(
            ticket_id=uuid.uuid4(),
            action="nope",  # type: ignore[arg-type]
            expires_at=datetime.now(tz=UTC),
        )
