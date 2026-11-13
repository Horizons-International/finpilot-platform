from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.services.async_executive_dashboard_service import (
    AsyncExecutiveDashboardService,
)
from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.executive_dashboard import ExecutiveDashboardResponse
from app.utils.enums import UserRole

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])
READ_ROLES = (UserRole.ADMINISTRATOR, UserRole.COMPLIANCE_OFFICER, UserRole.AUDITOR)


@router.get(
    "/executive-dashboard", response_model=APIResponse[ExecutiveDashboardResponse]
)
async def get_executive_dashboard(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    department: str | None = Query(default=None, min_length=1, max_length=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*READ_ROLES, resource_type="executive-dashboard")
    ),
) -> APIResponse[ExecutiveDashboardResponse]:
    service = AsyncExecutiveDashboardService(db, UUID(current_user["tenant_id"]))
    dashboard = await service.get_dashboard(
        start_date=start_date, end_date=end_date, department=department
    )
    return APIResponse(
        success=True,
        message="Executive dashboard retrieved successfully.",
        data=dashboard,
    )
