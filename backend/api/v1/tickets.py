import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status

from backend.api.deps import TicketServiceDep
from backend.api.security import require_api_key
from backend.api.v1.schemas.ticket import (
    TicketAcceptedResponse,
    TicketCreateRequest,
    TicketResponse,
)
from backend.services.ticket import CreateTicketRequest, TicketService

router = APIRouter(
    prefix="/tickets",
    tags=["tickets"],
    dependencies=[Depends(require_api_key)],
)


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TicketAcceptedResponse,
)
async def create_ticket(
    request: TicketCreateRequest,
    idempotency_key: str = Header(),
    service: TicketService = TicketServiceDep,
) -> TicketAcceptedResponse:
    result = await service.create_ticket(
        idempotency_key=idempotency_key,
        request=CreateTicketRequest(
            user_id=request.user_id,
            stake_amount=request.stake_amount,
            currency=request.currency.value,
            selections=[s.model_dump(mode="json") for s in request.selections],
        ),
    )
    ticket = result.ticket
    return TicketAcceptedResponse(
        ticket_id=ticket.id,
        status=ticket.status,
        created_at=ticket.created_at,
    )


@router.get(
    "/{ticket_id}",
    response_model=TicketResponse,
)
async def get_ticket(
    ticket_id: uuid.UUID,
    service: TicketService = TicketServiceDep,
) -> TicketResponse:
    ticket = await service.get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="ticket_not_found"
        )
    return TicketResponse.model_validate(ticket)
