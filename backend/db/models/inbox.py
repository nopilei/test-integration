import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class ProcessedProviderMessage(Base):
    """Inbox для дедупликации входящих сообщений провайдера по message_id.

    Строка вставляется в той же транзакции, что и первый side effect
    обработки сообщения, поэтому claim атомарен с изменением статуса тикета.
    """

    __tablename__ = "processed_provider_messages"
    __table_args__ = (
        # для периодической чистки по ретеншну
        Index("ix_processed_provider_messages_processed_at", "processed_at"),
    )

    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    message_type: Mapped[str] = mapped_column(String(64), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
