from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.analytics.repositories.executive_dashboard_repository import (
    ExecutiveDashboardRepository,
)
from app.schemas.executive_dashboard import (
    ComplianceAMLAlerts,
    ComplianceOverview,
    ComplianceRiskDistribution,
    CustomerGrowthTrendPoint,
    CustomerOverview,
    CustomerVerificationStatus,
    ExecutiveDashboardFilters,
    ExecutiveDashboardResponse,
    OperationsOverview,
    SLAPerformance,
    TeamWorkload,
    WorkflowStatusOverview,
)
from app.utils.date_time import utc_now
from app.utils.errors import bad_request


class ExecutiveDashboardService:
    DEFAULT_LOOKBACK_DAYS = 30
    MAX_LOOKBACK_DAYS = 366

    def __init__(self, db: Session) -> None:
        self.repository = ExecutiveDashboardRepository(db)

    @staticmethod
    def _percentage(
        numerator: int,
        denominator: int,
    ) -> float | None:
        if denominator == 0:
            return None

        return round((numerator / denominator) * 100, 2)

    def get_dashboard(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        department: str | None = None,
    ) -> ExecutiveDashboardResponse:
        normalized_end_date = end_date or utc_now().date()

        normalized_start_date = start_date or (
            normalized_end_date - timedelta(days=self.DEFAULT_LOOKBACK_DAYS - 1)
        )

        if normalized_start_date > normalized_end_date:
            raise bad_request(
                "start_date cannot be after end_date.",
            )

        lookback_days = (normalized_end_date - normalized_start_date).days + 1

        if lookback_days > self.MAX_LOOKBACK_DAYS:
            raise bad_request(
                "Dashboard date range cannot exceed 366 days.",
            )

        normalized_department = (
            department.strip()
            if department is not None and department.strip()
            else None
        )

        customer_trend = self.repository.get_customer_trend(
            start_date=normalized_start_date,
            end_date=normalized_end_date,
        )

        customer_snapshot = self.repository.get_latest_customer_snapshot(
            end_date=normalized_end_date,
        )

        compliance_snapshot = self.repository.get_latest_compliance_snapshot(
            end_date=normalized_end_date,
        )

        operations_snapshot = self.repository.get_latest_operations_snapshot(
            end_date=normalized_end_date,
        )

        task_sla_metrics = self.repository.get_task_sla_metrics(
            start_date=normalized_start_date,
            end_date=normalized_end_date,
        )

        workflow_sla_metrics = self.repository.get_workflow_sla_metrics(
            start_date=normalized_start_date,
            end_date=normalized_end_date,
        )

        team_workload = self.repository.get_team_workload(
            end_date=normalized_end_date,
            department=normalized_department,
        )

        if customer_trend:
            first_customer_snapshot = customer_trend[0]
            last_customer_snapshot = customer_trend[-1]

            customer_growth = (
                last_customer_snapshot.ending_total_customers
                - first_customer_snapshot.ending_total_customers
            )

            customer_growth_percentage = self._percentage(
                customer_growth,
                first_customer_snapshot.ending_total_customers,
            )
        else:
            customer_growth = 0
            customer_growth_percentage = None

        customer_snapshot = customer_snapshot
        compliance_snapshot = compliance_snapshot
        operations_snapshot = operations_snapshot

        customer_overview = CustomerOverview(
            ending_total_customers=(
                customer_snapshot.ending_total_customers if customer_snapshot else 0
            ),
            customer_growth=customer_growth,
            customer_growth_percentage=customer_growth_percentage,
            verification_status=CustomerVerificationStatus(
                ending_pending_verification_customers=(
                    customer_snapshot.ending_pending_verification_customers
                    if customer_snapshot
                    else 0
                ),
                ending_verified_customers=(
                    customer_snapshot.ending_verified_customers
                    if customer_snapshot
                    else 0
                ),
                ending_suspended_customers=(
                    customer_snapshot.ending_suspended_customers
                    if customer_snapshot
                    else 0
                ),
                ending_rejected_customers=(
                    customer_snapshot.ending_rejected_customers
                    if customer_snapshot
                    else 0
                ),
            ),
            growth_trend=[
                CustomerGrowthTrendPoint(
                    snapshot_date=row.snapshot_date,
                    ending_total_customers=row.ending_total_customers,
                    customers_registered_during_day=(
                        row.customers_registered_during_day
                    ),
                    verification_approvals_during_day=(
                        row.verification_approvals_during_day
                    ),
                )
                for row in customer_trend
            ],
        )

        compliance_overview = ComplianceOverview(
            ending_total_cases=(
                compliance_snapshot.ending_total_cases if compliance_snapshot else 0
            ),
            ending_open_cases=(
                compliance_snapshot.ending_open_cases if compliance_snapshot else 0
            ),
            ending_resolved_cases=(
                compliance_snapshot.ending_resolved_cases if compliance_snapshot else 0
            ),
            ending_closed_cases=(
                compliance_snapshot.ending_closed_cases if compliance_snapshot else 0
            ),
            risk_distribution=ComplianceRiskDistribution(
                ending_low_risk_customers=(
                    compliance_snapshot.ending_low_risk_customers
                    if compliance_snapshot
                    else 0
                ),
                ending_medium_risk_customers=(
                    compliance_snapshot.ending_medium_risk_customers
                    if compliance_snapshot
                    else 0
                ),
                ending_high_risk_customers=(
                    compliance_snapshot.ending_high_risk_customers
                    if compliance_snapshot
                    else 0
                ),
                ending_critical_risk_customers=(
                    compliance_snapshot.ending_critical_risk_customers
                    if compliance_snapshot
                    else 0
                ),
            ),
            aml_alerts=ComplianceAMLAlerts(
                ending_total_alerts=(
                    compliance_snapshot.ending_total_alerts
                    if compliance_snapshot
                    else 0
                ),
                ending_low_severity_alerts=(
                    compliance_snapshot.ending_low_severity_alerts
                    if compliance_snapshot
                    else 0
                ),
                ending_medium_severity_alerts=(
                    compliance_snapshot.ending_medium_severity_alerts
                    if compliance_snapshot
                    else 0
                ),
                ending_high_severity_alerts=(
                    compliance_snapshot.ending_high_severity_alerts
                    if compliance_snapshot
                    else 0
                ),
                ending_critical_severity_alerts=(
                    compliance_snapshot.ending_critical_severity_alerts
                    if compliance_snapshot
                    else 0
                ),
            ),
        )

        operations_overview = OperationsOverview(
            workflow_status=WorkflowStatusOverview(
                ending_active_workflows=(
                    operations_snapshot.ending_active_workflows
                    if operations_snapshot
                    else 0
                ),
                ending_total_completed_workflows=(
                    operations_snapshot.ending_total_completed_workflows
                    if operations_snapshot
                    else 0
                ),
                ending_total_failed_workflows=(
                    operations_snapshot.ending_total_failed_workflows
                    if operations_snapshot
                    else 0
                ),
            ),
            sla_performance=SLAPerformance(
                tasks_completed_during_period=task_sla_metrics["tasks_completed"],
                tasks_completed_within_sla_during_period=task_sla_metrics[
                    "tasks_completed_within_sla"
                ],
                tasks_completed_breached_sla_during_period=task_sla_metrics[
                    "tasks_completed_breached_sla"
                ],
                task_sla_compliance_percentage=self._percentage(
                    task_sla_metrics["tasks_completed_within_sla"],
                    task_sla_metrics["tasks_completed"],
                ),
                workflows_completed_during_period=workflow_sla_metrics[
                    "workflows_completed"
                ],
                workflows_completed_within_sla_during_period=(
                    workflow_sla_metrics["workflows_completed_within_sla"]
                ),
                workflows_completed_breached_sla_during_period=(
                    workflow_sla_metrics["workflows_completed_breached_sla"]
                ),
                workflow_sla_compliance_percentage=self._percentage(
                    workflow_sla_metrics["workflows_completed_within_sla"],
                    workflow_sla_metrics["workflows_completed"],
                ),
            ),
            team_workload=[
                TeamWorkload(
                    team=team,
                    user_role=user_role,
                    open_tasks=open_tasks,
                    overdue_tasks=overdue_tasks,
                )
                for team, user_role, open_tasks, overdue_tasks in team_workload
            ],
        )

        return ExecutiveDashboardResponse(
            generated_at=utc_now(),
            filters=ExecutiveDashboardFilters(
                start_date=normalized_start_date,
                end_date=normalized_end_date,
                department=normalized_department,
            ),
            customer_overview=customer_overview,
            compliance_overview=compliance_overview,
            operations_overview=operations_overview,
        )
