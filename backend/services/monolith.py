import asyncio
import logging
import random
import uuid
from dataclasses import dataclass

from backend.config import settings
from backend.constants import RecommendationAction

logger = logging.getLogger(__name__)


class MonolithError(Exception):
    pass


@dataclass
class TicketProcessingResult:
    ok: bool
    detail: str | None = None


class FakeMonolithClient:
    """Фейковый клиент к монолиту"""

    def __init__(
            self,
            time_multiplier: int = settings.monolith_mock_time_multiplier,
            error_rate: int = settings.monolith_mock_error_rate,
    ):
        self._time_multiplier = time_multiplier
        self._error_rate = error_rate

    async def process_ticket(
        self,
        ticket_id: uuid.UUID,
        action: RecommendationAction | None = None,
        provider_reason: str | None = None,
    ) -> TicketProcessingResult:
        await asyncio.sleep(random.random() * self._time_multiplier)
        self._maybe_fail("settle")
        return TicketProcessingResult(ok=True, detail=f"settled as {action}")

    def _maybe_fail(self, op: str) -> None:
        if random.random() < self._error_rate:
            logger.warning("Simulated monolith failure on %s", op)
            raise MonolithError
