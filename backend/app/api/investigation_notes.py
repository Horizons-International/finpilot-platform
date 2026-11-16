from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.investigation_note import (
    InvestigationNoteCreate,
    InvestigationNoteResponse,
)
from app.services.async_investigation_note_service import AsyncInvestigationNoteService
from app.utils.enums import UserRole
from app.utils.errors import unauthorized

router = APIRouter(prefix="/api/v1", tags=["Investigation Notes"])


def _authenticated_values(
    current_user: dict[str, Any],
) -> tuple[UUID, str, UserRole, UUID]:
    try:
        user_id = UUID(str(current_user["sub"]))
        tenant_id = UUID(str(current_user["tenant_id"]))
        role = UserRole(str(current_user.get("role")))
    except (KeyError, TypeError, ValueError) as exc:
        raise unauthorized("Invalid authenticated user.") from exc

    email = current_user.get("email")
    if not isinstance(email, str) or not email:
        raise unauthorized("Authenticated user email is missing.")
    return user_id, email, role, tenant_id


def _request_metadata(request: Request) -> tuple[str | None, str | None]:
    return (
        request.client.host if request.client is not None else None,
        request.headers.get("user-agent"),
    )


@router.post(
    "/customers/{customer_id}/verification-cases/{case_id}/investigation-notes",
    response_model=APIResponse[InvestigationNoteResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Add an investigation note",
    description=(
        "Only the reviewer currently assigned to the "
        "verification case can create notes."
    ),
)
async def create_investigation_note(
    customer_id: UUID,
    case_id: UUID,
    payload: InvestigationNoteCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.REVIEWER, resource_type="investigation_note")
    ),
) -> APIResponse[InvestigationNoteResponse]:
    user_id, email, _role, tenant_id = _authenticated_values(current_user)
    ip_address, user_agent = _request_metadata(request)
    note = await AsyncInvestigationNoteService(db, tenant_id).create_note(
        customer_id=customer_id,
        case_id=case_id,
        user_id=user_id,
        user_email=email,
        activity_type=payload.activity_type,
        note=payload.note,
        attachment_reference=payload.attachment_reference,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return APIResponse(
        success=True,
        message="Investigation note created successfully.",
        data=InvestigationNoteResponse.model_validate(note),
    )


@router.get(
    "/customers/{customer_id}/verification-cases/{case_id}/investigation-notes",
    response_model=APIResponse[list[InvestigationNoteResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get investigation notes",
    description=(
        "Administrators and compliance officers can view any tenant case. "
        "Reviewers can view cases assigned to them."
    ),
)
async def get_investigation_notes(
    customer_id: UUID,
    case_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="investigation_note",
        )
    ),
) -> APIResponse[list[InvestigationNoteResponse]]:
    user_id, email, role, tenant_id = _authenticated_values(current_user)
    ip_address, user_agent = _request_metadata(request)
    notes = await AsyncInvestigationNoteService(db, tenant_id).get_notes(
        customer_id=customer_id,
        case_id=case_id,
        user_id=user_id,
        user_role=role,
        user_email=email,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return APIResponse(
        success=True,
        message="Investigation notes retrieved successfully.",
        data=[InvestigationNoteResponse.model_validate(item) for item in notes],
    )
