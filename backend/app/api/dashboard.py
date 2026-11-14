"""Native-async operations dashboard API."""

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.services.async_dashboard_service import AsyncDashboardService
from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.dashboard import OperationsDashboardResponse
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["Dashboard"],
)


@router.get(
    "/operations",
    response_model=APIResponse[OperationsDashboardResponse],
    summary="Get operations dashboard",
    description="Retrieve operational dashboard metrics.",
)
async def get_operations_dashboard(
    start_date: date | None = Query(
        default=None,
        description="Inclusive start date in UTC.",
    ),
    end_date: date | None = Query(
        default=None,
        description="Inclusive end date in UTC.",
    ),
    country: str | None = Query(
        default=None,
        min_length=1,
        max_length=100,
        description="Customer country of residence.",
    ),
    user_role: UserRole | None = Query(
        default=None,
        description="Filter assigned/started operational work by user role.",
    ),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="dashboard",
        )
    ),
) -> APIResponse[OperationsDashboardResponse]:
    dashboard = await AsyncDashboardService(
        db, UUID(current_user["tenant_id"])
    ).get_operations_dashboard(
        start_date=start_date,
        end_date=end_date,
        country=country,
        user_role=user_role,
    )
    return APIResponse(
        success=True,
        message="Operations dashboard retrieved successfully.",
        data=dashboard,
    )
