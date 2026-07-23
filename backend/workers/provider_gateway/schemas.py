import enum
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from backend.constants import ProviderMessageType, RecommendationAction


class ProviderErrorCode(str, enum.Enum):
    TICKET_EXPIRED = "ticket_expired"
    PROVIDER_BUSY = "provider_busy"
    RISK_ENGINE_TIMEOUT = "risk_engine_timeout"
    INVALID_TICKET = "invalid_ticket"


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    market: str
    odds: Decimal


class TicketPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_id: uuid.UUID
    user_id: uuid.UUID
    stake_amount: Decimal
    currency: str
    selections: list[Selection]
    placed_at: datetime


class RecommendationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_id: uuid.UUID
    action: RecommendationAction
    reason: str | None = None
    expires_at: datetime


class ConfirmRecommendationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_id: uuid.UUID


class DeclineRecommendationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_id: uuid.UUID


class RequestCancellationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_id: uuid.UUID
    reason: str


class CancellationAppliedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_id: uuid.UUID


class AckPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ack_of: uuid.UUID  # message_id being acknowledged
    status: Literal["ok", "error"]
    error_code: ProviderErrorCode | None = None
    error_detail: str | None = None


class ProviderAckError(Exception):
    def __init__(self, ack: AckPayload) -> None:
        super().__init__(f"{ack.error_code}: {ack.error_detail}")
        self.ack = ack


PayloadT = Union[
    TicketPayload,
    RecommendationPayload,
    ConfirmRecommendationPayload,
    DeclineRecommendationPayload,
    RequestCancellationPayload,
    CancellationAppliedPayload,
    AckPayload,
]


_PAYLOAD_BY_TYPE: dict[ProviderMessageType, type[BaseModel]] = {
    ProviderMessageType.TICKET: TicketPayload,
    ProviderMessageType.RECOMMENDATION: RecommendationPayload,
    ProviderMessageType.CONFIRM_RECOMMENDATION: ConfirmRecommendationPayload,
    ProviderMessageType.DECLINE_RECOMMENDATION: DeclineRecommendationPayload,
    ProviderMessageType.REQUEST_CANCELLATION: RequestCancellationPayload,
    ProviderMessageType.CANCELLATION_APPLIED: CancellationAppliedPayload,
    ProviderMessageType.ACK: AckPayload,
}


class Message(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    ticket_id: uuid.UUID | None = None
    type: ProviderMessageType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    payload: dict[str, Any]

    @classmethod
    def build(
        cls,
        payload: BaseModel,
        type: ProviderMessageType,
        message_id: uuid.UUID | None = None,
        ticket_id: uuid.UUID | None = None,
    ) -> "Message":
        return cls(
            message_id=message_id or uuid.uuid4(),
            ticket_id=ticket_id,
            type=type,
            payload=payload.model_dump(mode="json"),
        )
