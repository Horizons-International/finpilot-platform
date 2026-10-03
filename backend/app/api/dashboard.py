from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_dashboard_service
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.dashboard import OperationsDashboardResponse
from app.services.dashboard_service import DashboardService
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
def get_operations_dashboard(
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
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="dashboard",
        )
    ),
    service: DashboardService = Depends(get_dashboard_service),
) -> APIResponse[OperationsDashboardResponse]:
    dashboard = service.get_operations_dashboard(
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
