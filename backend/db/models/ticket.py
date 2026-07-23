import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.constants import Currency, RecommendationAction, TicketStatus
from backend.db.base import Base, TimestampMixin


class Ticket(TimestampMixin, Base):
    """Игровой тикет в рамках интеграции с risk-провайдером.

    Поле status — единственный источник правды по жизненному циклу тикета;
    reconciler может безопасно опрашивать его.
    """

    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_tickets_idempotency_key"),
        CheckConstraint("stake_amount > 0", name="stake_amount_positive"),
        Index("ix_tickets_status", "status"),
        Index("ix_tickets_status_updated_at", "status", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    stake_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[Currency] = mapped_column(
        Enum(
            Currency,
            name="currency",
            native_enum=False,
            length=3,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
    )
    selections: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus, name="ticket_status", native_enum=False, length=32),
        nullable=False,
        default=TicketStatus.NEW,
    )

    provider_recommendation: Mapped[RecommendationAction | None] = mapped_column(
        Enum(
            RecommendationAction,
            name="recommendation_action",
            native_enum=False,
            length=16,
        ),
        nullable=True,
    )
    provider_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    provider_recommendation_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    settled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_reason: Mapped[str | None] = mapped_column(String(1024), nullable=True)
