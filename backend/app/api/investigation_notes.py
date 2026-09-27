from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.investigation_note import (
    InvestigationNoteCreate,
    InvestigationNoteResponse,
)
from app.services.investigation_note_service import (
    InvestigationNoteService,
)
from app.utils.enums import UserRole
from app.utils.errors import unauthorized

router = APIRouter(
    prefix="/api/v1",
    tags=["Investigation Notes"],
)


def _get_authenticated_user(
    current_user: dict[str, Any],
) -> tuple[UUID, str]:
    raw_user_id = current_user["sub"]

    try:
        user_id = UUID(str(raw_user_id))
    except (TypeError, ValueError):
        raise unauthorized("Invalid authenticated user.")

    email = current_user["email"]

    if not isinstance(email, str) or not email:
        raise unauthorized(
            "Authenticated user email is missing.",
        )

    return user_id, email


def _get_authenticated_role(
    current_user: dict[str, Any],
) -> UserRole:
    raw_role = current_user.get("role")

    try:
        return UserRole(str(raw_role))
    except ValueError:
        raise unauthorized("Invalid authenticated user role.")


def _request_metadata(
    request: Request,
) -> tuple[str | None, str | None]:
    client_host = request.client.host if request.client is not None else None

    user_agent = request.headers.get("user-agent")

    return client_host, user_agent


@router.post(
    "/customers/{customer_id}/verification-cases/{case_id}/investigation-notes",
    response_model=APIResponse[InvestigationNoteResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Add an investigation note",
    description=(
        "Add an investigation note, action, or resolution "
        "comment to a verification case. Only the reviewer "
        "currently assigned to the case can create notes."
    ),
)
def create_investigation_note(
    customer_id: UUID,
    case_id: UUID,
    payload: InvestigationNoteCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(UserRole.REVIEWER, resource_type="investigation_note")
    ),
) -> APIResponse[InvestigationNoteResponse]:
    user_id, email = _get_authenticated_user(current_user)

    ip_address, user_agent = _request_metadata(request)

    service = InvestigationNoteService(db)

    note = service.create_note(
        customer_id=customer_id,
        case_id=case_id,
        user_id=user_id,
        user_email=email,
        activity_type=payload.activity_type,
        note=payload.note,
        attachment_reference=(payload.attachment_reference),
        ip_address=ip_address,
        user_agent=user_agent,
    )

    response = InvestigationNoteResponse.model_validate(note)

    return APIResponse(
        success=True,
        message="Investigation note created successfully.",
        data=response,
    )


@router.get(
    "/customers/{customer_id}/verification-cases/{case_id}/investigation-notes",
    response_model=APIResponse[list[InvestigationNoteResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get investigation notes",
    description=(
        "Return the investigation activity history for a "
        "verification case. Administrators and compliance "
        "officers can view any case. Reviewers can view "
        "cases assigned to them."
    ),
)
def get_investigation_notes(
    customer_id: UUID,
    case_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="investigation_note",
        )
    ),
) -> APIResponse[list[InvestigationNoteResponse]]:
    user_id, _ = _get_authenticated_user(current_user)

    user_role = _get_authenticated_role(current_user)

    service = InvestigationNoteService(db)

    notes = service.get_notes(
        customer_id=customer_id,
        case_id=case_id,
        user_id=user_id,
        user_role=user_role,
    )

    response = [InvestigationNoteResponse.model_validate(note) for note in notes]

    return APIResponse(
        success=True,
        message=("Investigation notes retrieved successfully."),
        data=response,
    )
