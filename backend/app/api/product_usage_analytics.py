"""Product usage dashboard and filterable feature reports."""

from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.analytics.services.product_usage_analytics_service import (
    ProductUsageAnalyticsService,
)
from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.product_usage_analytics import (
    ProductUsageDashboardResponse,
    ProductUsageFeatureReport,
)
from app.utils.enums import UserRole
from app.utils.errors import forbidden

router = APIRouter(
    prefix="/api/v1/product-analytics",
    tags=["Product Usage Analytics"],
)

READ_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.ORGANIZATION_ADMIN,
    UserRole.COMPLIANCE_MANAGER,
    UserRole.COMPLIANCE_OFFICER,
    UserRole.REVIEWER,
    UserRole.ANALYST,
    UserRole.VIEWER,
    UserRole.AUDITOR,
    UserRole.CUSTOMER_SUCCESS_MANAGER,
    UserRole.PRODUCT_MANAGER,
)


def _service(
    db: Session,
    current_user: dict[str, Any],
    selected_tenant_id: UUID | None,
) -> ProductUsageAnalyticsService:
    owner_tenant_id = UUID(current_user["tenant_id"])
    is_platform_admin = current_user.get("is_platform_admin") is True
    # A role label by itself must never grant cross-tenant visibility: bank-level
    # user-management flows may also assign ordinary roles. Use the trusted flag.
    cross_tenant_access = is_platform_admin
    if not cross_tenant_access and selected_tenant_id not in (None, owner_tenant_id):
        raise forbidden("You can only view product usage for your own tenant.")
    filter_tenant_id = selected_tenant_id if cross_tenant_access else owner_tenant_id
    return ProductUsageAnalyticsService(
        db,
        owner_tenant_id=owner_tenant_id,
        cross_tenant_access=cross_tenant_access,
        tenant_filter_id=filter_tenant_id,
    )


def _date_defaults(
    start_date: date | None,
    end_date: date | None,
) -> tuple[date, date]:
    today = datetime.now(timezone.utc).date()
    resolved_end = end_date or today
    resolved_start = start_date or max(today - timedelta(days=29), date(2000, 1, 1))
    return resolved_start, resolved_end


@router.get(
    "/dashboard",
    response_model=APIResponse[ProductUsageDashboardResponse],
    summary="Get date-filtered customer product usage dashboard",
    description=(
        "Shows active users, login frequency, API calls, verification requests, "
        "AI requests, workflow runs, report exports, and most/unused features. "
        "Cross-tenant queries require the trusted platform-admin flag; ordinary "
        "users, including Product Managers without that flag, remain tenant-scoped."
    ),
)
def get_product_usage_dashboard(
    start_date: date | None = Query(
        default=None, description="Inclusive UTC calendar date."
    ),
    end_date: date | None = Query(
        default=None, description="Inclusive UTC calendar date."
    ),
    tenant_id: UUID | None = Query(
        default=None,
        description=(
            "Optional tenant filter; cross-tenant filtering requires elevated access."
        ),
    ),
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*READ_ROLES, resource_type="product-analytics")
    ),
) -> APIResponse[ProductUsageDashboardResponse]:
    start, end = _date_defaults(start_date, end_date)
    service = _service(db, current_user, tenant_id)
    data = service.dashboard(start_date=start, end_date=end)
    return APIResponse(
        success=True,
        message="Product usage dashboard retrieved successfully.",
        data=data,
    )


@router.get(
    "/features",
    response_model=APIResponse[ProductUsageFeatureReport],
    summary="Get most-used and unused product features",
)
def get_product_feature_report(
    start_date: date | None = Query(
        default=None, description="Inclusive UTC calendar date."
    ),
    end_date: date | None = Query(
        default=None, description="Inclusive UTC calendar date."
    ),
    tenant_id: UUID | None = Query(
        default=None,
        description=(
            "Optional tenant filter; cross-tenant filtering requires elevated access."
        ),
    ),
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*READ_ROLES, resource_type="product-analytics")
    ),
) -> APIResponse[ProductUsageFeatureReport]:
    start, end = _date_defaults(start_date, end_date)
    service = _service(db, current_user, tenant_id)
    data = service.feature_report(start_date=start, end_date=end)
    return APIResponse(
        success=True,
        message="Product feature usage report retrieved successfully.",
        data=data,
    )
