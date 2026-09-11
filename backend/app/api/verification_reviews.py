from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.dependencies import get_verification_review_service
from app.core.responses import APIResponse
from app.core.security import UserRole, require_roles
from app.schemas.verification_review import (
    VerificationReviewCreate,
    VerificationReviewResponse,
)
from app.services.verification_review_service import (
    VerificationReviewService,
)

router = APIRouter(
    prefix=(
        "/api/v1/customers/{customer_id}"
        "/verification-cases/{verification_case_id}/reviews"
    ),
    tags=["Verification Reviews"],
)


@router.post(
    "/start",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
    summary="Start verification case review",
)
def start_review(
    customer_id: UUID,
    verification_case_id: UUID,
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.REVIEWER,
            resource_type="verification_review",
        )
    ),
    service: VerificationReviewService = Depends(get_verification_review_service),
) -> APIResponse[None]:
    reviewer_id = UUID(current_user["sub"])

    service.start_review(
        customer_id=customer_id,
        verification_case_id=verification_case_id,
        reviewer_id=reviewer_id,
        email=current_user["email"],
    )

    return APIResponse(
        success=True,
        message="Verification review started successfully.",
        data=None,
    )


@router.post(
    "",
    response_model=APIResponse[VerificationReviewResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Review a verification case",
)
def create_review(
    customer_id: UUID,
    verification_case_id: UUID,
    review_data: VerificationReviewCreate,
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.REVIEWER,
            resource_type="verification_review",
        )
    ),
    service: VerificationReviewService = Depends(get_verification_review_service),
) -> APIResponse[VerificationReviewResponse]:
    reviewer_id = UUID(current_user["sub"])

    review = service.create_review(
        customer_id=customer_id,
        verification_case_id=verification_case_id,
        reviewer_id=reviewer_id,
        email=current_user["email"],
        decision=review_data.decision,
        notes=review_data.notes,
    )

    return APIResponse(
        success=True,
        message="Verification review created successfully.",
        data=VerificationReviewResponse.model_validate(review),
    )
