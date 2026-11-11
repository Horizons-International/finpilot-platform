from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.core.async_dependencies import get_async_verification_service
from app.core.async_security import require_async_roles
from app.core.responses import APIResponse
from app.providers.schemas import VerificationResponse
from app.schemas.verification_case import (
    VerificationCaseCreate,
    VerificationCaseInitiation,
    VerificationCaseResponse,
    VerificationCaseStatusUpdate,
)
from app.services.async_verification_service import AsyncVerificationService
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/customers/{customer_id}/verification-cases",
    tags=["Verification Cases"],
)
verification_router = APIRouter(
    prefix="/api/v1/customers/{customer_id}",
    tags=["Verification"],
)


@router.post(
    "",
    response_model=APIResponse[VerificationCaseResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create verification case",
    description="Create an identity verification case for a customer.",
)
async def create_verification_case(
    request: Request,
    customer_id: UUID,
    case_data: VerificationCaseCreate,
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="verification_case",
        )
    ),
    service: AsyncVerificationService = Depends(get_async_verification_service),
) -> APIResponse[VerificationCaseResponse]:
    case = await service.create_case(
        customer_id=customer_id,
        case_data=case_data,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
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
async def get_verification_cases(
    customer_id: UUID,
    _: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="verification_case",
        )
    ),
    service: AsyncVerificationService = Depends(get_async_verification_service),
) -> APIResponse[list[VerificationCaseResponse]]:
    cases = await service.get_cases_by_customer(customer_id)
    return APIResponse(
        success=True,
        message="Verification cases retrieved successfully.",
        data=[VerificationCaseResponse.model_validate(case) for case in cases],
    )


@router.patch(
    "/{case_id}/status",
    response_model=APIResponse[VerificationCaseResponse],
    status_code=status.HTTP_200_OK,
    summary="Patch verification case status",
    description="Updates verification case status.",
)
async def update_verification_case_status(
    customer_id: UUID,
    case_id: UUID,
    request: Request,
    status_data: VerificationCaseStatusUpdate,
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="verification_case",
        )
    ),
    service: AsyncVerificationService = Depends(get_async_verification_service),
) -> APIResponse[VerificationCaseResponse]:
    case = await service.update_status(
        customer_id=customer_id,
        case_id=case_id,
        status_data=status_data,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return APIResponse(
        success=True,
        message="Verification case status updated successfully.",
        data=VerificationCaseResponse.model_validate(case),
    )


@verification_router.post(
    "/verification",
    response_model=APIResponse[VerificationCaseResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Initiate verification case",
    description="Initiate verification case by ID.",
)
async def initiate_verification(
    request: Request,
    customer_id: UUID,
    verification_data: VerificationCaseInitiation,
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="verification_case",
        )
    ),
    service: AsyncVerificationService = Depends(get_async_verification_service),
) -> APIResponse[VerificationCaseResponse]:
    case = await service.initiate_verification(
        customer_id=customer_id,
        verification_data=verification_data,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return APIResponse(
        success=True,
        message="Verification initiated successfully.",
        data=VerificationCaseResponse.model_validate(case),
    )


@router.post(
    "/{verification_case_id}/provider-verification",
    response_model=APIResponse[VerificationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Submit verification case",
    description="Submits verification case to provider.",
)
async def submit_provider_verification(
    request: Request,
    customer_id: UUID,
    verification_case_id: UUID,
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="verification_case",
        )
    ),
    service: AsyncVerificationService = Depends(get_async_verification_service),
) -> APIResponse[VerificationResponse]:
    result = await service.submit_to_provider(
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        customer_id=customer_id,
        verification_case_id=verification_case_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return APIResponse(
        success=True,
        message="Verification submitted to provider.",
        data=result,
    )
