from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.analytics.services.compliance_analytics_service import (
    ComplianceAnalyticsService,
)
from app.core.dependencies import get_compliance_analytics_service
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.compliance_analytics import ComplianceAnalyticsResponse
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/analytics",
    tags=["Analytics"],
)


READ_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.COMPLIANCE_OFFICER,
)


@router.get(
    "/compliance",
    response_model=APIResponse[ComplianceAnalyticsResponse],
    summary="Get compliance analytics",
    description=(
        "Retrieve compliance analytics including risk distribution, "
        "AML alert trends, case resolution performance, and "
        "verification rejection reasons."
    ),
)
def get_compliance_analytics(
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
            resource_type="compliance-analytics",
        )
    ),
    service: ComplianceAnalyticsService = Depends(
        get_compliance_analytics_service,
    ),
) -> APIResponse[ComplianceAnalyticsResponse]:
    analytics = service.get_analytics(
        start_date=start_date,
        end_date=end_date,
    )

    return APIResponse(
        success=True,
        message="Compliance analytics retrieved successfully.",
        data=analytics,
    )
