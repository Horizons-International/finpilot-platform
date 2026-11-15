"""Async orchestration for the filtered operations dashboard."""

from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.repositories.async_dashboard_repository import (
    AsyncDashboardRepository,
)
from app.schemas.dashboard import (
    DashboardComplianceMetrics,
    DashboardCustomerMetrics,
    DashboardTaskMetrics,
    DashboardWorkflowMetrics,
    OperationsDashboardFilters,
    OperationsDashboardResponse,
)
from app.utils.date_time import utc_now
from app.utils.enums import UserRole
from app.utils.errors import bad_request


class AsyncDashboardService:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active_tenant = db.info.get("tenant_id")
        if active_tenant is not None and active_tenant != tenant_id:
            raise ValueError("Dashboard service tenant does not match session tenant.")
        db.info["tenant_id"] = tenant_id
        self.repository = AsyncDashboardRepository(db, tenant_id)

    async def get_operations_dashboard(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        country: str | None = None,
        user_role: UserRole | None = None,
    ) -> OperationsDashboardResponse:
        if start_date is not None and end_date is not None and start_date > end_date:
            raise bad_request("start_date cannot be after end_date.")

        normalized_country = (
            country.strip() if country is not None and country.strip() else None
        )
        metrics = await self.repository.get_metrics(
            start_date=start_date,
            end_date=end_date,
            country=normalized_country,
            user_role=user_role,
        )
        return OperationsDashboardResponse(
            generated_at=utc_now(),
            filters=OperationsDashboardFilters(
                start_date=start_date,
                end_date=end_date,
                country=normalized_country,
                user_role=user_role.value if user_role else None,
            ),
            customers=DashboardCustomerMetrics(
                total_customers=metrics["total_customers"],
                new_registrations=metrics["new_registrations"],
                pending_verification=metrics["pending_verification"],
                verified_customers=metrics["verified_customers"],
            ),
            workflows=DashboardWorkflowMetrics(
                active_workflows=metrics["active_workflows"],
                completed_workflows=metrics["completed_workflows"],
                failed_workflows=metrics["failed_workflows"],
            ),
            tasks=DashboardTaskMetrics(
                open_tasks=metrics["open_tasks"],
                completed_tasks=metrics["completed_tasks"],
                overdue_tasks=metrics["overdue_tasks"],
            ),
            compliance=DashboardComplianceMetrics(
                open_cases=metrics["open_cases"],
                high_risk_customers=metrics["high_risk_customers"],
                pending_reviews=metrics["pending_reviews"],
            ),
        )
