from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.analytics.services.compliance_analytics_service import (
    ComplianceAnalyticsService,
)
from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.compliance_analytics import ComplianceAnalyticsResponse
from app.services.async_service_bridge import run_sync_in_tenant
from app.utils.enums import UserRole

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])
READ_ROLES = (UserRole.ADMINISTRATOR, UserRole.COMPLIANCE_OFFICER)


@router.get("/compliance", response_model=APIResponse[ComplianceAnalyticsResponse])
async def get_compliance_analytics(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*READ_ROLES, resource_type="compliance-analytics")
    ),
) -> APIResponse[ComplianceAnalyticsResponse]:
    tenant_id = UUID(current_user["tenant_id"])

    def operation(sync_db: Session):
        return ComplianceAnalyticsService(sync_db, tenant_id).get_analytics(
            start_date=start_date,
            end_date=end_date,
        )

    analytics = await run_sync_in_tenant(db, tenant_id, operation)
    return APIResponse(
        success=True,
        message="Compliance analytics retrieved successfully.",
        data=analytics,
    )
