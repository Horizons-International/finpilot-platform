from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.dashboard_repository import DashboardRepository
from app.schemas.dashboard import (
    DashboardComplianceMetrics,
    DashboardCustomerMetrics,
    DashboardTaskMetrics,
    DashboardWorkflowMetrics,
    OperationsDashboardFilters,
    OperationsDashboardResponse,
)
from app.services.tenant_context import resolve_tenant_context
from app.utils.date_time import utc_now
from app.utils.enums import UserRole
from app.utils.errors import bad_request


class DashboardService:
    def __init__(self, db: Session, tenant_id: UUID | None = None) -> None:
        self.db = db
        self._requested_tenant_id = tenant_id
        self.tenant_id: UUID | None = tenant_id
        self.repository: DashboardRepository | None = None

    def _repository(self) -> DashboardRepository:
        if self.repository is None:
            self.tenant_id = resolve_tenant_context(
                self.db, self._requested_tenant_id, resource_name="operations dashboard"
            )
            self.repository = DashboardRepository(self.db, tenant_id=self.tenant_id)
        return self.repository

    def get_operations_dashboard(
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
        metrics = self._repository().get_metrics(
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
