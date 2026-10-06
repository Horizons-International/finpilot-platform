from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.analytics.services.customer_analytics_service import (
    CustomerAnalyticsService,
)
from app.core.dependencies import get_customer_analytics_service
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.customer_analytics import CustomerAnalyticsResponse
from app.utils.enums import CustomerStatus, UserRole

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
    "/customer-summary",
    response_model=APIResponse[CustomerAnalyticsResponse],
    summary="Get customer analytics",
    description=(
        "Retrieve customer overview and lifecycle analytics "
        "with optional date, country, and customer-status filters."
    ),
)
def get_customer_summary(
    start_date: date | None = Query(
        default=None,
        description="Inclusive analytics start date in UTC.",
    ),
    end_date: date | None = Query(
        default=None,
        description="Inclusive analytics end date in UTC.",
    ),
    country: str | None = Query(
        default=None,
        min_length=1,
        max_length=100,
        description="Customer country of residence.",
    ),
    status: CustomerStatus | None = Query(
        default=None,
        description="Filter customer population by customer status.",
    ),
    _: dict[str, Any] = Depends(
        require_roles(
            *READ_ROLES,
            resource_type="customer-analytics",
        )
    ),
    service: CustomerAnalyticsService = Depends(
        get_customer_analytics_service,
    ),
) -> APIResponse[CustomerAnalyticsResponse]:
    analytics = service.get_customer_summary(
        start_date=start_date,
        end_date=end_date,
        country=country,
        status=status,
    )

    return APIResponse(
        success=True,
        message="Customer analytics retrieved successfully.",
        data=analytics,
    )
