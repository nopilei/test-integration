import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from backend.constants import Currency, RecommendationAction, TicketStatus

StakeAmount = Annotated[
    Decimal,
    Field(gt=Decimal("0"), le=Decimal("999999999999.99"), max_digits=18, decimal_places=2),
]
EventId = Annotated[str, StringConstraints(min_length=1, max_length=128)]
Market = Annotated[str, StringConstraints(min_length=1, max_length=128)]


class SelectionIn(BaseModel):
    event_id: EventId
    market: Market
    odds: Decimal


class TicketCreateRequest(BaseModel):
    user_id: uuid.UUID
    stake_amount: StakeAmount
    currency: Currency
    selections: list[SelectionIn] = Field(min_length=1, max_length=20)


class TicketAcceptedResponse(BaseModel):
    ticket_id: uuid.UUID
    status: TicketStatus
    created_at: datetime


class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    idempotency_key: str
    user_id: uuid.UUID
    stake_amount: Decimal
    currency: Currency
    selections: list[dict]
    status: TicketStatus
    provider_recommendation: RecommendationAction | None
    provider_reason: str | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime
    provider_recommendation_at: datetime | None
    settled_at: datetime | None
    confirmed_at: datetime | None
    cancelled_at: datetime | None
