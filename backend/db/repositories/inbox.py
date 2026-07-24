import uuid
from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models.inbox import ProcessedProviderMessage


class InboxRepository:
    """Дедупликация входящих сообщений провайдера по message_id."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def try_claim(
        self,
        message_id: uuid.UUID,
        message_type: str,
        ticket_id: uuid.UUID | None,
    ) -> bool:
        """Попытаться занять message_id. Возвращает False, если сообщение уже обработано.

        Коммит намеренно не делается: строка фиксируется первым commit()
        вызывающего кода, т.е. атомарно с side effect'ами обработки.
        Конкурентный дубль повиснет на локе строки до коммита первого
        обработчика и затем получит конфликт.
        """
        stmt = (
            pg_insert(ProcessedProviderMessage)
            .values(
                message_id=message_id,
                message_type=message_type,
                ticket_id=ticket_id,
            )
            .on_conflict_do_nothing(index_elements=["message_id"])
            .returning(ProcessedProviderMessage.message_id)
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none() is not None

