from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.verification_case_assignment import (
    AssignedVerificationCaseResponse,
    AssignedVerificationCasesResponse,
    VerificationCaseAssignmentHistoryResponse,
    VerificationCaseAssignmentRequest,
    VerificationCaseAssignmentResponse,
)
from app.services.verification_case_assignment_service import (
    VerificationCaseAssignmentService,
)
from app.utils.enums import UserRole
from app.utils.errors import unauthorized

router = APIRouter(
    prefix="/api/v1",
    tags=["Verification Case Assignments"],
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


def _request_metadata(
    request: Request,
) -> tuple[str | None, str | None]:
    client_host = request.client.host if request.client is not None else None

    user_agent = request.headers.get("user-agent")

    return client_host, user_agent


@router.patch(
    "/customers/{customer_id}/verification-cases/{verification_case_id}/assignment",
    response_model=APIResponse[VerificationCaseAssignmentResponse],
    status_code=status.HTTP_200_OK,
    summary="Assign a verification case",
    description=(
        "Assign or reassign a verification case to an active "
        "reviewer. Only administrators and compliance officers "
        "can perform case assignments."
    ),
)
def assign_verification_case(
    customer_id: UUID,
    verification_case_id: UUID,
    payload: VerificationCaseAssignmentRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="verification_case",
        )
    ),
) -> APIResponse[VerificationCaseAssignmentResponse]:
    user_id, email = _get_authenticated_user(
        current_user,
    )

    ip_address, user_agent = _request_metadata(request)

    service = VerificationCaseAssignmentService(db)

    history = service.assign_case(
        customer_id=customer_id,
        verification_case_id=verification_case_id,
        reviewer_id=payload.assigned_to,
        assigned_by=user_id,
        assigned_by_email=email,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    response = VerificationCaseAssignmentResponse(
        verification_case_id=history.verification_case_id,
        assigned_to=history.assigned_to,
        assigned_at=history.assigned_at,
        assigned_by=history.assigned_by,
        previous_reviewer=history.previous_reviewer,
    )

    return APIResponse(
        success=True,
        message="Verification case assigned successfully.",
        data=response,
    )


@router.get(
    "/customers/{customer_id}/verification-cases/"
    "{verification_case_id}/assignment-history",
    response_model=APIResponse[list[VerificationCaseAssignmentHistoryResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get verification case assignment history",
    description=(
        "Return the complete assignment and reassignment "
        "history for a verification case."
    ),
)
def get_verification_case_assignment_history(
    customer_id: UUID,
    verification_case_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="verification_case",
        )
    ),
) -> APIResponse[list[VerificationCaseAssignmentHistoryResponse]]:
    service = VerificationCaseAssignmentService(db)

    history = service.get_assignment_history(
        customer_id=customer_id,
        verification_case_id=verification_case_id,
    )

    response = [
        VerificationCaseAssignmentHistoryResponse.model_validate(item)
        for item in history
    ]

    return APIResponse(
        success=True,
        message=("Verification case assignment history retrieved successfully."),
        data=response,
    )


@router.get(
    "/verification-cases/assigned-to-me",
    response_model=APIResponse[AssignedVerificationCasesResponse],
    status_code=status.HTTP_200_OK,
    summary="Get assigned verification cases",
    description=(
        "Return verification cases currently assigned to the authenticated user."
    ),
)
def get_my_assigned_verification_cases(
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="verification_case",
        )
    ),
) -> APIResponse[AssignedVerificationCasesResponse]:
    user_id, _ = _get_authenticated_user(current_user)

    service = VerificationCaseAssignmentService(db)

    cases = service.get_assigned_cases(user_id)

    response_cases = [
        AssignedVerificationCaseResponse(
            verification_case_id=case.id,
            customer_id=case.customer_id,
            verification_type=case.verification_type.value,
            status=case.status.value,
            assigned_to=case.assigned_to,
            assigned_at=case.assigned_at,
            assigned_by=case.assigned_by,
            created_at=case.created_at,
            updated_at=case.updated_at,
            completed_at=case.completed_at,
        )
        for case in cases
        if case.assigned_to is not None
    ]

    response = AssignedVerificationCasesResponse(
        total=len(response_cases),
        cases=response_cases,
    )

    return APIResponse(
        success=True,
        message="Assigned verification cases retrieved successfully.",
        data=response,
    )


@router.get(
    "/verification-cases/assigned",
    response_model=APIResponse[AssignedVerificationCasesResponse],
    status_code=status.HTTP_200_OK,
    summary="Get all assigned verification cases",
    description=(
        "Return all currently assigned verification cases "
        "for workload management. Only administrators and "
        "compliance officers can access this endpoint."
    ),
)
def get_all_assigned_verification_cases(
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="verification_case",
        )
    ),
) -> APIResponse[AssignedVerificationCasesResponse]:
    service = VerificationCaseAssignmentService(db)

    cases = service.get_all_assigned_cases()

    response_cases = [
        AssignedVerificationCaseResponse(
            verification_case_id=case.id,
            customer_id=case.customer_id,
            verification_type=case.verification_type.value,
            status=case.status.value,
            assigned_to=case.assigned_to,
            assigned_at=case.assigned_at,
            assigned_by=case.assigned_by,
            created_at=case.created_at,
            updated_at=case.updated_at,
            completed_at=case.completed_at,
        )
        for case in cases
        if case.assigned_to is not None
    ]

    response = AssignedVerificationCasesResponse(
        total=len(response_cases),
        cases=response_cases,
    )

    return APIResponse(
        success=True,
        message=("Assigned verification cases retrieved successfully."),
        data=response,
    )
