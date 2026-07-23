import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.constants import TERMINAL_TICKET_STATUSES, TicketStatus
from backend.db.models.ticket import Ticket


class TicketRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, ticket: Ticket) -> Ticket:
        self._session.add(ticket)
        await self._session.flush()
        return ticket

    async def get_by_id(self, ticket_id: uuid.UUID) -> Ticket | None:
        stmt = select(Ticket).where(Ticket.id == ticket_id)
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_id_for_update(self, ticket_id: uuid.UUID) -> Ticket | None:
        """Заблокировать строку в текущей транзакции. Вызывать только внутри tx."""
        stmt = select(Ticket).where(Ticket.id == ticket_id).with_for_update()
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_idempotency_key(self, key: str) -> Ticket | None:
        stmt = select(Ticket).where(Ticket.idempotency_key == key)
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def find_stuck(
        self,
        older_than: datetime,
        limit: int = 100,
    ) -> Sequence[Ticket]:
        stmt = (
            select(Ticket)
            .where(
                Ticket.status.not_in(TERMINAL_TICKET_STATUSES),
                Ticket.updated_at < older_than,
            )
            .order_by(Ticket.updated_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        res = await self._session.execute(stmt)
        return res.scalars().all()

    async def count_by_status(self) -> dict[TicketStatus, int]:
        from sqlalchemy import func

        stmt = select(Ticket.status, func.count()).group_by(Ticket.status)
        res = await self._session.execute(stmt)
        return {row[0]: row[1] for row in res.all()}


def stale_threshold(now: datetime, seconds: int) -> datetime:
    return now - timedelta(seconds=seconds)
