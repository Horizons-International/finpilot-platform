from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.services.async_operations_analytics_service import (
    AsyncOperationsAnalyticsService,
)
from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.operations_analytics import OperationsAnalyticsResponse
from app.utils.enums import UserRole

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])
READ_ROLES = (UserRole.ADMINISTRATOR, UserRole.COMPLIANCE_OFFICER, UserRole.AUDITOR)


@router.get(
    "/operations-performance", response_model=APIResponse[OperationsAnalyticsResponse]
)
async def get_operations_performance(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*READ_ROLES, resource_type="operations-analytics")
    ),
) -> APIResponse[OperationsAnalyticsResponse]:
    service = AsyncOperationsAnalyticsService(db, UUID(current_user["tenant_id"]))
    analytics = await service.get_operations_performance(
        start_date=start_date, end_date=end_date
    )
    return APIResponse(
        success=True,
        message="Operations performance analytics retrieved successfully.",
        data=analytics,
    )
