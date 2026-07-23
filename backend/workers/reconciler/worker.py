import asyncio
import logging
from datetime import UTC, datetime, timedelta

from backend.config import settings
from backend.db.repositories.ticket import TicketRepository
from backend.db.session import session_scope
from backend.observability.metrics import ticket_stuck_recovered_total
from backend.services.monolith import FakeMonolithClient
from backend.services.ticket import TicketService

logger = logging.getLogger(__name__)


class ReconcilerWorker:
    """Делает запросы на отмену в провайдер для тикетов которые застряли между статусами из-за ошибок."""

    def __init__(
        self,
        monolith: FakeMonolithClient,
        poll_interval: float = settings.reconciler_poll_interval_sec,
        stuck_after_sec: int = settings.reconciler_stuck_after_sec,
        batch_size: int = settings.reconciler_batch_size,
    ) -> None:
        self._monolith = monolith
        self._poll_interval = poll_interval
        self._stuck_after_sec = stuck_after_sec
        self._batch_size = batch_size
        self._stop = asyncio.Event()

    async def run(self) -> None:
        logger.info(
            "reconciler started (poll=%ss, stuck_after=%ss)",
            self._poll_interval, self._stuck_after_sec,
        )
        while not self._stop.is_set():
            try:
                await self._tick_once()
            except Exception:
                logger.exception("reconciler tick failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._poll_interval)
            except asyncio.TimeoutError:
                pass

    def request_stop(self) -> None:
        self._stop.set()

    async def _tick_once(self) -> None:
        await self._recover_stuck_tickets()

    async def _recover_stuck_tickets(self) -> None:
        threshold = datetime.now(tz=UTC) - timedelta(seconds=self._stuck_after_sec)

        async with session_scope() as session:
            repo = TicketRepository(session)
            stuck = await repo.find_stuck(older_than=threshold, limit=self._batch_size)
            service = TicketService(session=session, monolith=self._monolith)
            for ticket in stuck:
                previous = ticket.status
                logger.warning(
                    "reconciler: ticket %s stuck in %s since %s — requesting cancellation",
                    ticket.id, previous.value, ticket.updated_at,
                )
                try:
                    await service.request_cancellation(
                        ticket.id, reason=f"reconciler: stuck in {previous.value}"
                    )
                    ticket_stuck_recovered_total.labels(
                        from_status=previous.value, action="cancel"
                    ).inc()
                except Exception:
                    logger.exception(
                        "reconciler failed to progress ticket %s", ticket.id
                    )
