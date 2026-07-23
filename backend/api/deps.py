from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import session_scope
from backend.services.ticket import TicketService


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_scope() as session:
        yield session


SessionDep = Depends(get_session)


def get_ticket_service(
    request: Request,
    session: AsyncSession = SessionDep,
) -> TicketService:
    monolith = request.app.state.monolith
    return TicketService(session=session, monolith=monolith)


TicketServiceDep = Depends(get_ticket_service)
