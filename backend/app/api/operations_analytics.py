from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.analytics.services.operations_analytics_service import (
    OperationsAnalyticsService,
)
from app.core.dependencies import get_operations_analytics_service
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.operations_analytics import (
    OperationsAnalyticsResponse,
)
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
    "/operations-performance",
    response_model=APIResponse[OperationsAnalyticsResponse],
    summary="Get operations performance analytics",
    description=(
        "Retrieve workflow, task, employee, SLA, and historical "
        "operational performance analytics."
    ),
)
def get_operations_performance(
    start_date: date | None = Query(
        default=None,
        description="Inclusive analytics start date in UTC.",
    ),
    end_date: date | None = Query(
        default=None,
        description="Inclusive analytics end date in UTC.",
    ),
    _: dict[str, Any] = Depends(
        require_roles(
            *READ_ROLES,
            resource_type="operations-analytics",
        )
    ),
    service: OperationsAnalyticsService = Depends(
        get_operations_analytics_service,
    ),
) -> APIResponse[OperationsAnalyticsResponse]:
    analytics = service.get_operations_performance(
        start_date=start_date,
        end_date=end_date,
    )

    return APIResponse(
        success=True,
        message="Operations performance analytics retrieved successfully.",
        data=analytics,
    )
