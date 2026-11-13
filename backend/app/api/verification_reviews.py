from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.core.security import UserRole
from app.schemas.verification_review import (
    VerificationReviewCreate,
    VerificationReviewResponse,
)
from app.services.async_verification_supporting_service import (
    AsyncVerificationReviewService,
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
    description="Starts verification case review.",
)
async def start_review(
    request: Request,
    customer_id: UUID,
    verification_case_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.REVIEWER,
            resource_type="verification_case",
        )
    ),
) -> APIResponse[None]:
    reviewer_id = UUID(current_user["sub"])
    service = AsyncVerificationReviewService(db, UUID(current_user["tenant_id"]))

    await service.start_review(
        customer_id=customer_id,
        verification_case_id=verification_case_id,
        reviewer_id=reviewer_id,
        email=current_user["email"],
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
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
    description="Creates verfication case review",
)
async def create_review(
    request: Request,
    customer_id: UUID,
    verification_case_id: UUID,
    review_data: VerificationReviewCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.REVIEWER,
            resource_type="verification_case",
        )
    ),
) -> APIResponse[VerificationReviewResponse]:
    reviewer_id = UUID(current_user["sub"])
    service = AsyncVerificationReviewService(db, UUID(current_user["tenant_id"]))

    review = await service.create_review(
        customer_id=customer_id,
        verification_case_id=verification_case_id,
        reviewer_id=reviewer_id,
        email=current_user["email"],
        decision=review_data.decision,
        notes=review_data.notes,
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Verification review created successfully.",
        data=VerificationReviewResponse.model_validate(review),
    )
