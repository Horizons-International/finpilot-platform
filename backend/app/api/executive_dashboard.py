from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.analytics.services.executive_dashboard_service import (
    ExecutiveDashboardService,
)
from app.core.dependencies import get_executive_dashboard_service
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.executive_dashboard import ExecutiveDashboardResponse
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/analytics",
    tags=["Analytics"],
)


READ_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.COMPLIANCE_OFFICER,
    UserRole.AUDITOR,
)


@router.get(
    "/executive-dashboard",
    response_model=APIResponse[ExecutiveDashboardResponse],
    summary="Get executive dashboard",
    description="Retrieve executive business performance dashboard data.",
)
def get_executive_dashboard(
    start_date: date | None = Query(
        default=None,
        description="Inclusive start date in UTC.",
    ),
    end_date: date | None = Query(
        default=None,
        description="Inclusive end date in UTC.",
    ),
    department: str | None = Query(
        default=None,
        min_length=1,
        max_length=100,
        description="Filter team workload by department.",
    ),
    _: dict[str, Any] = Depends(
        require_roles(
            *READ_ROLES,
            resource_type="executive-dashboard",
        )
    ),
    service: ExecutiveDashboardService = Depends(
        get_executive_dashboard_service,
    ),
) -> APIResponse[ExecutiveDashboardResponse]:
    dashboard = service.get_dashboard(
        start_date=start_date,
        end_date=end_date,
        department=department,
    )

    return APIResponse(
        success=True,
        message="Executive dashboard retrieved successfully.",
        data=dashboard,
    )
