import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.constants import OutboxStatus
from backend.db.models.outbox import OutboxEvent


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        entity_id: uuid.UUID,
        event_type: str,
        routing_key: str,
        payload: dict[str, Any],
    ) -> OutboxEvent:
        event = OutboxEvent(
            entity_id=entity_id,
            event_type=event_type,
            routing_key=routing_key,
            payload=payload,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def fetch_pending(self, limit: int) -> Sequence[OutboxEvent]:
        """Атомарно забрать пачку pending-событий через SKIP LOCKED."""
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.status == OutboxStatus.PENDING)
            .order_by(OutboxEvent.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        res = await self._session.execute(stmt)
        return res.scalars().all()

    async def mark_published_many(self, event_ids: Sequence[uuid.UUID]) -> None:
        if not event_ids:
            return
        stmt = (
            update(OutboxEvent)
            .where(OutboxEvent.id.in_(event_ids))
            .values(
                status=OutboxStatus.PUBLISHED,
                published_at=datetime.now(tz=UTC),
                last_error=None,
            )
        )
        await self._session.execute(stmt)

    async def mark_failed(
        self, event_id: uuid.UUID, error: str, max_attempts: int = 3
    ) -> None:
        new_attempts = OutboxEvent.attempts + 1
        stmt = (
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .values(
                attempts=new_attempts,
                last_error=error[:2000],
                status=case(
                    (new_attempts >= max_attempts, OutboxStatus.FAILED),
                    else_=OutboxEvent.status,
                ),
            )
        )
        await self._session.execute(stmt)
