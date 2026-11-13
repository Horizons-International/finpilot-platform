"""Native-async customer support ticket operations and attachment access."""

from typing import Annotated, Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.async_security import get_async_current_user
from app.core.database import get_async_db
from app.core.dependencies import get_storage
from app.core.responses import APIResponse
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
from app.services.async_support_ticket_attachment_service import (
    AsyncSupportTicketAttachmentService,
)
from app.services.async_support_ticket_service import AsyncSupportTicketService
from app.storages.base_storage import BaseStorage
from app.utils.enums import SupportTicketStatus

router = APIRouter(prefix="/api/v1/support/tickets", tags=["Customer Support"])


def _claims(actor: User) -> dict[str, Any]:
    return {
        "sub": str(actor.id),
        "tenant_id": str(actor.tenant_id),
        "role": str(getattr(actor.role, "value", actor.role)),
        "email": actor.email,
    }


def _service(db: AsyncSession, actor: User) -> AsyncSupportTicketService:
    return AsyncSupportTicketService(db, _claims(actor))


@router.post(
    "",
    response_model=APIResponse[SupportTicketResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_ticket(
    payload: SupportTicketCreate,
    db: AsyncSession = Depends(get_async_db),
    actor: User = Depends(get_async_current_user),
) -> APIResponse[SupportTicketResponse]:
    ticket = await _service(db, actor).create_ticket(payload)
    return APIResponse(
        success=True,
        message="Support ticket created successfully.",
        data=SupportTicketResponse.model_validate(ticket),
    )


@router.get("", response_model=APIResponse[list[SupportTicketResponse]])
async def list_tickets(
    ticket_status: Annotated[SupportTicketStatus | None, Query(alias="status")] = None,
    category: TicketCategory | None = Query(default=None),
    priority: TicketPriority | None = Query(default=None),
    assigned_to: UUID | None = Query(default=None),
    tenant_id: UUID | None = Query(default=None, description="Support-Agent filter"),
    db: AsyncSession = Depends(get_async_db),
    actor: User = Depends(get_async_current_user),
) -> APIResponse[list[SupportTicketResponse]]:
    rows = await _service(db, actor).list_tickets(
        status_value=ticket_status.value if ticket_status else None,
        category=category,
        priority=priority,
        assigned_to=assigned_to,
        tenant_id=tenant_id,
    )
    return APIResponse(
        success=True,
        message="Support tickets retrieved successfully.",
        data=[SupportTicketResponse.model_validate(row) for row in rows],
    )


@router.get("/{ticket_id}", response_model=APIResponse[SupportTicketResponse])
async def get_ticket(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    actor: User = Depends(get_async_current_user),
) -> APIResponse[SupportTicketResponse]:
    row = await _service(db, actor).get_ticket(ticket_id)
    return APIResponse(
        success=True,
        message="Support ticket retrieved successfully.",
        data=SupportTicketResponse.model_validate(row),
    )


@router.patch(
    "/{ticket_id}/assignment", response_model=APIResponse[SupportTicketResponse]
)
async def assign_ticket(
    ticket_id: UUID,
    payload: SupportTicketAssignmentUpdate,
    db: AsyncSession = Depends(get_async_db),
    actor: User = Depends(get_async_current_user),
) -> APIResponse[SupportTicketResponse]:
    row = await _service(db, actor).assign_ticket(ticket_id, payload.assigned_to)
    return APIResponse(
        success=True,
        message="Support ticket assignment updated successfully.",
        data=SupportTicketResponse.model_validate(row),
    )


@router.patch("/{ticket_id}/status", response_model=APIResponse[SupportTicketResponse])
async def update_ticket_status(
    ticket_id: UUID,
    payload: SupportTicketStatusUpdate,
    db: AsyncSession = Depends(get_async_db),
    actor: User = Depends(get_async_current_user),
) -> APIResponse[SupportTicketResponse]:
    row = await _service(db, actor).update_status(ticket_id, payload.status)
    return APIResponse(
        success=True,
        message="Support ticket status updated successfully.",
        data=SupportTicketResponse.model_validate(row),
    )


@router.post(
    "/{ticket_id}/comments",
    response_model=APIResponse[SupportTicketCommentResponse],
    status_code=status.HTTP_201_CREATED,
)
async def add_ticket_comment(
    ticket_id: UUID,
    payload: SupportTicketCommentCreate,
    db: AsyncSession = Depends(get_async_db),
    actor: User = Depends(get_async_current_user),
) -> APIResponse[SupportTicketCommentResponse]:
    row = await _service(db, actor).add_comment(ticket_id, payload)
    return APIResponse(
        success=True,
        message="Support ticket comment added successfully.",
        data=SupportTicketCommentResponse.model_validate(row),
    )


@router.get(
    "/{ticket_id}/comments",
    response_model=APIResponse[list[SupportTicketCommentResponse]],
)
async def list_ticket_comments(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    actor: User = Depends(get_async_current_user),
) -> APIResponse[list[SupportTicketCommentResponse]]:
    rows = await _service(db, actor).list_comments(ticket_id)
    return APIResponse(
        success=True,
        message="Support ticket comments retrieved successfully.",
        data=[SupportTicketCommentResponse.model_validate(row) for row in rows],
    )


@router.get(
    "/{ticket_id}/history",
    response_model=APIResponse[list[SupportTicketHistoryResponse]],
)
async def list_ticket_history(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    actor: User = Depends(get_async_current_user),
) -> APIResponse[list[SupportTicketHistoryResponse]]:
    rows = await _service(db, actor).list_history(ticket_id)
    return APIResponse(
        success=True,
        message="Support ticket history retrieved successfully.",
        data=[SupportTicketHistoryResponse.model_validate(row) for row in rows],
    )


@router.post(
    "/{ticket_id}/attachments",
    response_model=APIResponse[SupportTicketAttachmentResponse],
    status_code=status.HTTP_201_CREATED,
)
async def upload_ticket_attachment(
    ticket_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_async_db),
    actor: User = Depends(get_async_current_user),
    storage: BaseStorage = Depends(get_storage),
) -> APIResponse[SupportTicketAttachmentResponse]:
    row = await AsyncSupportTicketAttachmentService(db, actor, storage).add_attachment(
        ticket_id, file
    )
    return APIResponse(
        success=True,
        message="Support ticket attachment uploaded successfully.",
        data=SupportTicketAttachmentResponse.model_validate(row),
    )


@router.get(
    "/{ticket_id}/attachments",
    response_model=APIResponse[list[SupportTicketAttachmentResponse]],
)
async def list_ticket_attachments(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    actor: User = Depends(get_async_current_user),
) -> APIResponse[list[SupportTicketAttachmentResponse]]:
    service = _service(db, actor)
    rows = await service.list_attachments(ticket_id)
    return APIResponse(
        success=True,
        message="Support ticket attachments retrieved successfully.",
        data=[SupportTicketAttachmentResponse.model_validate(row) for row in rows],
    )


@router.get(
    "/{ticket_id}/attachments/{attachment_id}/download", response_class=Response
)
async def download_ticket_attachment(
    ticket_id: UUID,
    attachment_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    actor: User = Depends(get_async_current_user),
    storage: BaseStorage = Depends(get_storage),
) -> Response:
    row = await _service(db, actor).get_attachment(ticket_id, attachment_id)
    content = await run_in_threadpool(storage.read, row.storage_path)
    filename = quote(row.original_filename, safe="")
    return Response(
        content=content,
        media_type=row.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
