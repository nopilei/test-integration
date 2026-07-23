import uuid

import pytest

from backend.constants import RecommendationAction
from backend.services.monolith import FakeMonolithClient, MonolithError


@pytest.mark.asyncio
async def test_monolith_succeeds_when_error_rate_zero():
    client = FakeMonolithClient(time_multiplier=0, error_rate=0)

    result = await client.process_ticket(
        uuid.uuid4(),
        action=RecommendationAction.ACCEPT,
    )
    assert result.ok is True


@pytest.mark.asyncio
async def test_monolith_raises_when_error_rate_one(monkeypatch):
    client = FakeMonolithClient(time_multiplier=0, error_rate=1)

    with pytest.raises(MonolithError):
        await client.process_ticket(uuid.uuid4(), action=RecommendationAction.DECLINE)
