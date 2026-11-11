from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.analytics.services.customer_analytics_service import CustomerAnalyticsService
from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.customer_analytics import CustomerAnalyticsResponse
from app.services.async_service_bridge import run_sync_in_tenant
from app.utils.enums import CustomerStatus, UserRole

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])
READ_ROLES = (UserRole.ADMINISTRATOR, UserRole.COMPLIANCE_OFFICER, UserRole.AUDITOR)


@router.get("/customer-summary", response_model=APIResponse[CustomerAnalyticsResponse])
async def get_customer_summary(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    country: str | None = Query(default=None, min_length=1, max_length=100),
    status: CustomerStatus | None = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*READ_ROLES, resource_type="customer-analytics")
    ),
) -> APIResponse[CustomerAnalyticsResponse]:
    tenant_id = UUID(current_user["tenant_id"])

    def operation(sync_db: Session):
        return CustomerAnalyticsService(sync_db, tenant_id).get_customer_summary(
            start_date=start_date,
            end_date=end_date,
            country=country,
            status=status,
        )

    analytics = await run_sync_in_tenant(db, tenant_id, operation)
    return APIResponse(
        success=True,
        message="Customer analytics retrieved successfully.",
        data=analytics,
    )
