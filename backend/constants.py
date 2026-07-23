import enum


class Currency(str, enum.Enum):
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"


class OutboxStatus(str, enum.Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"


class TicketStatus(str, enum.Enum):
    """Возможные статусы тикета.

    Успешный путь:
        NEW -> SENT_TO_PROVIDER -> RECOMMENDED_CONFIRM|RECOMMENDED_DECLINE
            -> SETTLED -> CONFIRMED|DECLINED

    (Если возникла проблема между RECOMMENDED_* и CONFIRMED):
        * -> CANCELLATION_REQUESTED -> CANCELLED
    """

    NEW = "new"
    SENT_TO_PROVIDER = "sent_to_provider"
    RECOMMENDED_CONFIRM = "recommended_confirm"
    RECOMMENDED_DECLINE = "recommended_decline"
    SETTLED = "settled"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    CANCELLATION_REQUESTED = "cancellation_requested"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


TERMINAL_TICKET_STATUSES: frozenset[TicketStatus] = frozenset(
    {
        TicketStatus.CONFIRMED,
        TicketStatus.DECLINED,
        TicketStatus.CANCELLED,
        TicketStatus.EXPIRED,
    }
)


class ProviderMessageType(str, enum.Enum):
    """Возможные типы сообщений для провайдера (запросы + ответы)."""

    TICKET = "TICKET"
    RECOMMENDATION = "RECOMMENDATION"
    CONFIRM_RECOMMENDATION = "CONFIRM_RECOMMENDATION"
    DECLINE_RECOMMENDATION = "DECLINE_RECOMMENDATION"
    REQUEST_CANCELLATION = "REQUEST_CANCELLATION"
    CANCELLATION_APPLIED = "CANCELLATION_APPLIED"
    ACK = "ACK"


class RecommendationAction(str, enum.Enum):
    ACCEPT = "accept"
    DECLINE = "decline"


EVENT_TYPE_TICKET_OUTBOUND = "ticket.outbound"
AGGREGATE_TYPE_TICKET = "ticket"
