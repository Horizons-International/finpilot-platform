from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.analytics.services.executive_dashboard_service import ExecutiveDashboardService
from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.executive_dashboard import ExecutiveDashboardResponse
from app.services.async_service_bridge import run_sync_in_tenant
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
    tenant_id = UUID(current_user["tenant_id"])

    def operation(sync_db: Session):
        return ExecutiveDashboardService(sync_db, tenant_id).get_dashboard(
            start_date=start_date,
            end_date=end_date,
            department=department,
        )

    dashboard = await run_sync_in_tenant(db, tenant_id, operation)
    return APIResponse(
        success=True,
        message="Executive dashboard retrieved successfully.",
        data=dashboard,
    )
