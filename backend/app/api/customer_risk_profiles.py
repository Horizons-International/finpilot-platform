from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.customer_risk_profile import (
    CustomerRiskProfileCreate,
    CustomerRiskProfileResponse,
)
from app.services.customer_risk_profile_service import (
    CustomerRiskProfileService,
)
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/customer-risk-profiles",
    tags=["Customer Risk Profiles"],
)


def get_customer_risk_profile_service(
    db: Session = Depends(get_db),
) -> CustomerRiskProfileService:
    return CustomerRiskProfileService(db)


@router.post(
    "",
    response_model=APIResponse[CustomerRiskProfileResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create customer risk profile",
    description="Creates a risk profile for a customer.",
)
def create_customer_risk_profile(
    payload: CustomerRiskProfileCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="risk profiles",
        )
    ),
    service: CustomerRiskProfileService = Depends(get_customer_risk_profile_service),
) -> APIResponse[CustomerRiskProfileResponse]:
    profile = service.create_profile(
        customer_id=payload.customer_id,
        risk_level=payload.risk_level,
        risk_score=payload.risk_score,
        risk_category=payload.risk_category,
        assessed_at=payload.assessed_at,
        assessment_source=payload.assessment_source,
        user_id=current_user["sub"],
        email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Customer risk profile created successfully.",
        data=CustomerRiskProfileResponse.model_validate(profile),
    )


@router.get(
    "/customer/{customer_id}",
    response_model=APIResponse[CustomerRiskProfileResponse],
    status_code=status.HTTP_200_OK,
    summary="Get customer risk profile",
    description="Retrieve risk profile for a customer.",
)
def get_customer_risk_profile(
    customer_id: UUID,
    service: CustomerRiskProfileService = Depends(get_customer_risk_profile_service),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="risk profile",
        )
    ),
) -> APIResponse[CustomerRiskProfileResponse]:
    profile = service.get_by_customer_id(customer_id)

    return APIResponse(
        success=True,
        message="Customer risk profile retrieved successfully.",
        data=CustomerRiskProfileResponse.model_validate(profile),
    )


@router.get(
    "/{profile_id}",
    response_model=APIResponse[CustomerRiskProfileResponse],
    status_code=status.HTTP_200_OK,
    summary="Get customer risk profile",
    description="Retrieve risk profile by ID.",
)
def get_customer_risk_profile_by_id(
    profile_id: UUID,
    service: CustomerRiskProfileService = Depends(get_customer_risk_profile_service),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="risk profile",
        )
    ),
) -> APIResponse[CustomerRiskProfileResponse]:
    profile = service.get_by_id(profile_id)

    return APIResponse(
        success=True,
        message="Customer risk profile retrieved successfully.",
        data=CustomerRiskProfileResponse.model_validate(profile),
    )


@router.get(
    "",
    response_model=APIResponse[list[CustomerRiskProfileResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get customer risk profiles",
    description="Retrieve all customer risk profiles",
)
def list_customer_risk_profiles(
    service: CustomerRiskProfileService = Depends(get_customer_risk_profile_service),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="risk profile",
        )
    ),
) -> APIResponse[list[CustomerRiskProfileResponse]]:
    profiles = service.get_all()

    return APIResponse(
        success=True,
        message="Customer risk profiles retrieved successfully.",
        data=[
            CustomerRiskProfileResponse.model_validate(profile) for profile in profiles
        ],
    )
