from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.analytics.services.operations_analytics_service import (
    OperationsAnalyticsService,
)
from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.operations_analytics import OperationsAnalyticsResponse
from app.services.async_service_bridge import run_sync_in_tenant
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
    tenant_id = UUID(current_user["tenant_id"])

    def operation(sync_db: Session):
        return OperationsAnalyticsService(
            sync_db, tenant_id
        ).get_operations_performance(
            start_date=start_date,
            end_date=end_date,
        )

    analytics = await run_sync_in_tenant(db, tenant_id, operation)
    return APIResponse(
        success=True,
        message="Operations performance analytics retrieved successfully.",
        data=analytics,
    )
