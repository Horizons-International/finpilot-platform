from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.ai_usage import AIUsageListResponse, AIUsageSummaryResponse
from app.services.async_ai_usage_query_service import AsyncAIUsageQueryService
from app.utils.enums import UserRole

router = APIRouter(prefix="/api/v1/ai-usage", tags=["AI Usage"])


def _service(db: AsyncSession, user: dict[str, Any]) -> AsyncAIUsageQueryService:
    return AsyncAIUsageQueryService(db, UUID(user["tenant_id"]))


@router.get(
    "",
    response_model=APIResponse[AIUsageListResponse],
    status_code=status.HTTP_200_OK,
    summary="Get AI usage",
    description="Retrieve tenant AI usage records.",
)
async def get_ai_usage(
    limit: int = Query(default=100, ge=1, le=500),
    user_id: UUID | None = Query(default=None),
    feature: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="ai_usage")
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[AIUsageListResponse]:
    result = await _service(db, current_user).get_usage(
        limit=limit, user_id=user_id, feature=feature
    )
    return APIResponse(
        success=True,
        message="AI usage retrieved successfully.",
        data=result,
    )


@router.get(
    "/summary",
    response_model=APIResponse[AIUsageSummaryResponse],
    status_code=status.HTTP_200_OK,
)
async def get_ai_usage_summary(
    user_id: UUID | None = Query(default=None),
    feature: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="ai_usage")
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[AIUsageSummaryResponse]:
    result = await _service(db, current_user).get_summary(
        user_id=user_id, feature=feature
    )
    return APIResponse(
        success=True,
        message="AI usage summary retrieved successfully.",
        data=result,
    )
