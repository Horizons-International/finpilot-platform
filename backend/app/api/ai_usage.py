from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import (
    get_ai_usage_service,
)
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.ai_usage import (
    AIUsageListResponse,
    AIUsageSummaryResponse,
)
from app.services.ai_usage_service import AIUsageService
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/ai-usage",
    tags=["AI Usage"],
)


@router.get(
    "",
    response_model=APIResponse[AIUsageListResponse],
    status_code=status.HTTP_200_OK,
    summary="Get AI usage",
    description="Retreive AI usage.",
)
def get_ai_usage(
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    user_id: UUID | None = Query(
        default=None,
    ),
    feature: str | None = Query(
        default=None,
    ),
    _current_user=Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
        ),
    ),
    service: AIUsageService = Depends(
        get_ai_usage_service,
    ),
):
    result = service.get_usage(
        limit=limit,
        user_id=user_id,
        feature=feature,
    )

    return APIResponse(
        success=True,
        message="AI usage retrieved successfully.",
        data=result,
    )


@router.get(
    "/summary",
    response_model=APIResponse[AIUsageSummaryResponse],
)
def get_ai_usage_summary(
    user_id: UUID | None = Query(
        default=None,
    ),
    feature: str | None = Query(
        default=None,
    ),
    _current_user=Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
        ),
    ),
    service: AIUsageService = Depends(
        get_ai_usage_service,
    ),
):
    result = service.get_summary(
        user_id=user_id,
        feature=feature,
    )

    return APIResponse(
        success=True,
        message="AI usage summary retrieved successfully.",
        data=result,
    )
