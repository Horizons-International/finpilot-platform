"""Customer support ticket API."""

from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_storage
from app.core.responses import APIResponse
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.support_ticket import (
    SupportTicketAssignmentUpdate,
    SupportTicketAttachmentResponse,
    SupportTicketCommentCreate,
    SupportTicketCommentResponse,
    SupportTicketCreate,
    SupportTicketHistoryResponse,
    SupportTicketResponse,
    SupportTicketStatusUpdate,
    TicketCategory,
    TicketPriority,
)
from app.services.support_ticket_service import SupportTicketService
from app.storages.base_storage import BaseStorage
from app.utils.enums import SupportTicketStatus, UserRole
from app.utils.errors import forbidden

router = APIRouter(prefix="/api/v1/support/tickets", tags=["Customer Support"])


def _service(db: Session, actor: User) -> SupportTicketService:
    return SupportTicketService(db, actor)


def _storage_service(
    db: Session, actor: User, storage: BaseStorage
) -> SupportTicketService:
    return SupportTicketService(db, actor, storage=storage)


def _require_staff_actor(actor: User) -> User:
    allowed = {
        UserRole.SUPPORT_AGENT.value,
        UserRole.ADMINISTRATOR.value,
        UserRole.ORGANIZATION_ADMIN.value,
        UserRole.CUSTOMER_SUCCESS_MANAGER.value,
    }
    role = str(getattr(actor.role, "value", actor.role))
    if role not in allowed:
        raise forbidden("Only support staff can perform this action.")
    return actor


@router.post(
    "",
    response_model=APIResponse[SupportTicketResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a customer support ticket",
)
def create_ticket(
    payload: SupportTicketCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> APIResponse[SupportTicketResponse]:
    ticket = _service(db, actor).create_ticket(payload)
    return APIResponse(
        success=True,
        message="Support ticket created successfully.",
        data=SupportTicketResponse.model_validate(ticket),
    )


@router.get(
    "",
    response_model=APIResponse[list[SupportTicketResponse]],
    summary="List tickets visible to the current user",
)
def list_tickets(
    ticket_status: Annotated[SupportTicketStatus | None, Query(alias="status")] = None,
    category: TicketCategory | None = Query(default=None),
    priority: TicketPriority | None = Query(default=None),
    assigned_to: UUID | None = Query(default=None),
    tenant_id: UUID | None = Query(default=None, description="Support-Agent filter"),
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> APIResponse[list[SupportTicketResponse]]:
    tickets = _service(db, actor).list_tickets(
        status_value=ticket_status.value if ticket_status else None,
        category=category,
        priority=priority,
        assigned_to=assigned_to,
        tenant_id=tenant_id,
    )
    return APIResponse(
        success=True,
        message="Support tickets retrieved successfully.",
        data=[SupportTicketResponse.model_validate(ticket) for ticket in tickets],
    )


@router.get(
    "/{ticket_id}",
    response_model=APIResponse[SupportTicketResponse],
    summary="Get one visible support ticket",
)
def get_ticket(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> APIResponse[SupportTicketResponse]:
    ticket = _service(db, actor).get_ticket(ticket_id)
    return APIResponse(
        success=True,
        message="Support ticket retrieved successfully.",
        data=SupportTicketResponse.model_validate(ticket),
    )


@router.patch(
    "/{ticket_id}/assignment",
    response_model=APIResponse[SupportTicketResponse],
    summary="Assign or unassign a support ticket",
)
def assign_ticket(
    ticket_id: UUID,
    payload: SupportTicketAssignmentUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> APIResponse[SupportTicketResponse]:
    _require_staff_actor(actor)
    ticket = _service(db, actor).assign_ticket(ticket_id, payload.assigned_to)
    return APIResponse(
        success=True,
        message="Support ticket assignment updated successfully.",
        data=SupportTicketResponse.model_validate(ticket),
    )


@router.patch(
    "/{ticket_id}/status",
    response_model=APIResponse[SupportTicketResponse],
    summary="Update a ticket's workflow status",
)
def update_ticket_status(
    ticket_id: UUID,
    payload: SupportTicketStatusUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> APIResponse[SupportTicketResponse]:
    _require_staff_actor(actor)
    ticket = _service(db, actor).update_status(ticket_id, payload.status)
    return APIResponse(
        success=True,
        message="Support ticket status updated successfully.",
        data=SupportTicketResponse.model_validate(ticket),
    )


@router.post(
    "/{ticket_id}/comments",
    response_model=APIResponse[SupportTicketCommentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Add a public comment or staff-only internal note",
)
def add_ticket_comment(
    ticket_id: UUID,
    payload: SupportTicketCommentCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> APIResponse[SupportTicketCommentResponse]:
    comment = _service(db, actor).add_comment(ticket_id, payload)
    return APIResponse(
        success=True,
        message="Support ticket comment added successfully.",
        data=SupportTicketCommentResponse.model_validate(comment),
    )


@router.get(
    "/{ticket_id}/comments",
    response_model=APIResponse[list[SupportTicketCommentResponse]],
    summary="List comments visible to the current user",
)
def list_ticket_comments(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> APIResponse[list[SupportTicketCommentResponse]]:
    comments = _service(db, actor).list_comments(ticket_id)
    return APIResponse(
        success=True,
        message="Support ticket comments retrieved successfully.",
        data=[
            SupportTicketCommentResponse.model_validate(comment) for comment in comments
        ],
    )


@router.get(
    "/{ticket_id}/history",
    response_model=APIResponse[list[SupportTicketHistoryResponse]],
    summary="List append-only ticket event history",
)
def list_ticket_history(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> APIResponse[list[SupportTicketHistoryResponse]]:
    events = _service(db, actor).list_history(ticket_id)
    return APIResponse(
        success=True,
        message="Support ticket history retrieved successfully.",
        data=[SupportTicketHistoryResponse.model_validate(event) for event in events],
    )


@router.post(
    "/{ticket_id}/attachments",
    response_model=APIResponse[SupportTicketAttachmentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Upload an attachment to a support ticket",
)
async def upload_ticket_attachment(
    ticket_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
    storage: BaseStorage = Depends(get_storage),
) -> APIResponse[SupportTicketAttachmentResponse]:
    attachment = await _storage_service(db, actor, storage).add_attachment(
        ticket_id, file
    )
    return APIResponse(
        success=True,
        message="Support ticket attachment uploaded successfully.",
        data=SupportTicketAttachmentResponse.model_validate(attachment),
    )


@router.get(
    "/{ticket_id}/attachments",
    response_model=APIResponse[list[SupportTicketAttachmentResponse]],
    summary="List attachments on a support ticket",
)
def list_ticket_attachments(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> APIResponse[list[SupportTicketAttachmentResponse]]:
    attachments = _service(db, actor).list_attachments(ticket_id)
    return APIResponse(
        success=True,
        message="Support ticket attachments retrieved successfully.",
        data=[
            SupportTicketAttachmentResponse.model_validate(attachment)
            for attachment in attachments
        ],
    )


@router.get(
    "/{ticket_id}/attachments/{attachment_id}/download",
    response_class=Response,
    summary="Download an attachment after ticket-level authorization",
)
def download_ticket_attachment(
    ticket_id: UUID,
    attachment_id: UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
    storage: BaseStorage = Depends(get_storage),
) -> Response:
    content, filename, content_type = _storage_service(
        db, actor, storage
    ).download_attachment(ticket_id, attachment_id)
    encoded_filename = quote(filename, safe="")
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
