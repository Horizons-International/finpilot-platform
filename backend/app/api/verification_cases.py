from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.dependencies import get_verification_service
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.verification_case import (
    VerificationCaseCreate,
    VerificationCaseResponse,
    VerificationCaseStatusUpdate,
)
from app.services.verification_service import VerificationService
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/customers/{customer_id}/verification-cases",
    tags=["Verification Cases"],
)


@router.post(
    "",
    response_model=APIResponse[VerificationCaseResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create verification case",
    description="Create an identity verification case for a customer.",
)
def create_verification_case(
    customer_id: UUID,
    case_data: VerificationCaseCreate,
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="case",
        )
    ),
    service: VerificationService = Depends(get_verification_service),
) -> APIResponse[VerificationCaseResponse]:
    case = service.create_case(
        customer_id=customer_id,
        case_data=case_data,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
    )

    return APIResponse(
        success=True,
        message="Verification case created successfully.",
        data=VerificationCaseResponse.model_validate(case),
    )


@router.get(
    "",
    response_model=APIResponse[list[VerificationCaseResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get customer verification cases",
    description="Retrieve all verification cases for a customer.",
)
def get_verification_cases(
    customer_id: UUID,
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="user",
        )
    ),
    service: VerificationService = Depends(get_verification_service),
) -> APIResponse[list[VerificationCaseResponse]]:
    cases = service.get_cases_by_customer(customer_id)

    return APIResponse(
        success=True,
        message="Verification cases retrieved successfully.",
        data=[VerificationCaseResponse.model_validate(case) for case in cases],
    )


@router.patch(
    "/{case_id}/status",
    response_model=APIResponse[VerificationCaseResponse],
    status_code=status.HTTP_200_OK,
)
def update_verification_case_status(
    customer_id: UUID,
    case_id: UUID,
    status_data: VerificationCaseStatusUpdate,
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
        )
    ),
    service: VerificationService = Depends(get_verification_service),
) -> APIResponse[VerificationCaseResponse]:
    case = service.update_status(
        customer_id=customer_id,
        case_id=case_id,
        status_data=status_data,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
    )

    return APIResponse(
        success=True,
        message="Verification case status updated successfully.",
        data=VerificationCaseResponse.model_validate(case),
    )
