from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.models.compliance_daily import ComplianceAnalyticsDaily
from app.analytics.models.customer_daily import CustomerAnalyticsDaily
from app.analytics.models.operations_daily import OperationsAnalyticsDaily
from app.models.aml_rule import AMLRule
from app.models.compliance_case import ComplianceCase
from app.models.customer import Customer
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.task import Task
from app.models.transaction_monitoring_result import (
    TransactionMonitoringResult,
)
from app.models.verification_case import IdentityVerificationCase
from app.models.workflow import WorkflowExecution
from app.utils.enums import (
    AMLRuleSeverity,
    ComplianceCaseStatus,
    CustomerRiskLevel,
    CustomerStatus,
    SLAStatus,
    TaskStatus,
    TransactionMonitoringOutcome,
    VerificationStatus,
    WorkflowExecutionStatus,
)


class AnalyticsSnapshotRepository:
    """Persistence and state-metric collection for daily analytics snapshots."""

    CUSTOMER_FIELDS = (
        "ending_total_customers",
        "customers_registered_during_day",
        "verification_approvals_during_day",
        "ending_pending_verification_customers",
        "ending_verified_customers",
        "ending_suspended_customers",
        "ending_rejected_customers",
    )

    COMPLIANCE_FIELDS = (
        "ending_total_cases",
        "cases_created_during_day",
        "ending_open_cases",
        "ending_resolved_cases",
        "ending_closed_cases",
        "ending_total_alerts",
        "alerts_created_during_day",
        "ending_low_severity_alerts",
        "ending_medium_severity_alerts",
        "ending_high_severity_alerts",
        "ending_critical_severity_alerts",
        "ending_low_risk_customers",
        "ending_medium_risk_customers",
        "ending_high_risk_customers",
        "ending_critical_risk_customers",
    )

    OPERATIONS_FIELDS = (
        "ending_total_tasks",
        "tasks_created_during_day",
        "ending_open_tasks",
        "ending_total_completed_tasks",
        "tasks_completed_during_day",
        "ending_overdue_tasks",
        "ending_tasks_sla_within_target",
        "ending_tasks_sla_approaching_deadline",
        "ending_tasks_sla_breached",
        "ending_tasks_sla_completed_on_time",
        "tasks_completed_within_sla_during_day",
        "tasks_completed_breached_sla_during_day",
        "ending_total_workflows",
        "workflows_started_during_day",
        "ending_active_workflows",
        "ending_total_completed_workflows",
        "workflows_completed_during_day",
        "ending_total_failed_workflows",
        "workflows_failed_during_day",
        "ending_workflows_sla_within_target",
        "ending_workflows_sla_approaching_deadline",
        "ending_workflows_sla_breached",
        "ending_workflows_sla_completed_on_time",
        "workflows_completed_within_sla_during_day",
        "workflows_completed_breached_sla_during_day",
    )

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _day_start(as_of: datetime) -> datetime:
        return as_of.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

    @staticmethod
    def _row_to_metrics(row: Any, fields: tuple[str, ...]) -> dict[str, int]:
        values = row._mapping

        return {field: int(values[field] or 0) for field in fields}

    @staticmethod
    def _count_filter(
        model: Any,
        *conditions: Any,
    ) -> Any:
        return func.count(model.id).filter(*conditions)

    def collect_customer_metrics(
        self,
        *,
        as_of: datetime,
    ) -> dict[str, int]:
        """Collect customer state and day-to-date activity."""

        day_start = self._day_start(as_of)

        statement = select(
            func.count(Customer.id).label(
                "ending_total_customers",
            ),
            self._count_filter(
                Customer,
                Customer.created_at >= day_start,
                Customer.created_at <= as_of,
            ).label(
                "customers_registered_during_day",
            ),
            func.count(Customer.id)
            .filter(
                Customer.status == CustomerStatus.PENDING_VERIFICATION,
            )
            .label(
                "ending_pending_verification_customers",
            ),
            func.count(Customer.id)
            .filter(
                Customer.status == CustomerStatus.VERIFIED,
            )
            .label(
                "ending_verified_customers",
            ),
            func.count(Customer.id)
            .filter(
                Customer.status == CustomerStatus.SUSPENDED,
            )
            .label(
                "ending_suspended_customers",
            ),
            func.count(Customer.id)
            .filter(
                Customer.status == CustomerStatus.REJECTED,
            )
            .label(
                "ending_rejected_customers",
            ),
        ).where(
            Customer.created_at <= as_of,
        )

        row = self.db.execute(statement).one()

        verification_approvals = (
            self.db.scalar(
                select(
                    func.count(IdentityVerificationCase.id),
                ).where(
                    IdentityVerificationCase.status == VerificationStatus.APPROVED,
                    IdentityVerificationCase.completed_at >= day_start,
                    IdentityVerificationCase.completed_at <= as_of,
                )
            )
            or 0
        )

        metrics = self._row_to_metrics(
            row,
            (
                "ending_total_customers",
                "customers_registered_during_day",
                "ending_pending_verification_customers",
                "ending_verified_customers",
                "ending_suspended_customers",
                "ending_rejected_customers",
            ),
        )

        metrics["verification_approvals_during_day"] = int(
            verification_approvals,
        )

        return metrics

    def collect_compliance_metrics(
        self,
        *,
        as_of: datetime,
    ) -> dict[str, int]:
        """Collect compliance, AML, and risk state and day-to-date activity."""

        day_start = self._day_start(as_of)

        open_statuses = (
            ComplianceCaseStatus.OPEN,
            ComplianceCaseStatus.ASSIGNED,
            ComplianceCaseStatus.UNDER_REVIEW,
            ComplianceCaseStatus.ESCALATED,
        )

        case_statement = select(
            func.count(ComplianceCase.id).label(
                "ending_total_cases",
            ),
            self._count_filter(
                ComplianceCase,
                ComplianceCase.created_at >= day_start,
                ComplianceCase.created_at <= as_of,
            ).label(
                "cases_created_during_day",
            ),
            func.count(ComplianceCase.id)
            .filter(
                ComplianceCase.status.in_(open_statuses),
            )
            .label(
                "ending_open_cases",
            ),
            func.count(ComplianceCase.id)
            .filter(
                ComplianceCase.status == ComplianceCaseStatus.RESOLVED,
            )
            .label(
                "ending_resolved_cases",
            ),
            func.count(ComplianceCase.id)
            .filter(
                ComplianceCase.status == ComplianceCaseStatus.CLOSED,
            )
            .label(
                "ending_closed_cases",
            ),
        ).where(
            ComplianceCase.created_at <= as_of,
        )

        case_row = self.db.execute(case_statement).one()

        alert_statement = (
            select(
                func.count(
                    TransactionMonitoringResult.id,
                ).label(
                    "ending_total_alerts",
                ),
                self._count_filter(
                    TransactionMonitoringResult,
                    TransactionMonitoringResult.created_at >= day_start,
                    TransactionMonitoringResult.created_at <= as_of,
                    TransactionMonitoringResult.result
                    == TransactionMonitoringOutcome.MATCHED,
                ).label(
                    "alerts_created_during_day",
                ),
                func.count(
                    TransactionMonitoringResult.id,
                )
                .filter(
                    AMLRule.severity == AMLRuleSeverity.LOW,
                )
                .label(
                    "ending_low_severity_alerts",
                ),
                func.count(
                    TransactionMonitoringResult.id,
                )
                .filter(
                    AMLRule.severity == AMLRuleSeverity.MEDIUM,
                )
                .label(
                    "ending_medium_severity_alerts",
                ),
                func.count(
                    TransactionMonitoringResult.id,
                )
                .filter(
                    AMLRule.severity == AMLRuleSeverity.HIGH,
                )
                .label(
                    "ending_high_severity_alerts",
                ),
                func.count(
                    TransactionMonitoringResult.id,
                )
                .filter(
                    AMLRule.severity == AMLRuleSeverity.CRITICAL,
                )
                .label(
                    "ending_critical_severity_alerts",
                ),
            )
            .select_from(TransactionMonitoringResult)
            .join(
                AMLRule,
                TransactionMonitoringResult.rule_id == AMLRule.id,
            )
            .where(
                TransactionMonitoringResult.result
                == TransactionMonitoringOutcome.MATCHED,
                TransactionMonitoringResult.created_at <= as_of,
            )
        )

        alert_row = self.db.execute(alert_statement).one()

        risk_statement = select(
            func.count(CustomerRiskProfile.id)
            .filter(
                CustomerRiskProfile.risk_level == CustomerRiskLevel.LOW,
            )
            .label(
                "ending_low_risk_customers",
            ),
            func.count(CustomerRiskProfile.id)
            .filter(
                CustomerRiskProfile.risk_level == CustomerRiskLevel.MEDIUM,
            )
            .label(
                "ending_medium_risk_customers",
            ),
            func.count(CustomerRiskProfile.id)
            .filter(
                CustomerRiskProfile.risk_level == CustomerRiskLevel.HIGH,
            )
            .label(
                "ending_high_risk_customers",
            ),
            func.count(CustomerRiskProfile.id)
            .filter(
                CustomerRiskProfile.risk_level == CustomerRiskLevel.CRITICAL,
            )
            .label(
                "ending_critical_risk_customers",
            ),
        ).where(
            CustomerRiskProfile.assessed_at <= as_of,
        )

        risk_row = self.db.execute(risk_statement).one()

        metrics = self._row_to_metrics(
            case_row,
            (
                "ending_total_cases",
                "cases_created_during_day",
                "ending_open_cases",
                "ending_resolved_cases",
                "ending_closed_cases",
            ),
        )

        metrics.update(
            self._row_to_metrics(
                alert_row,
                (
                    "ending_total_alerts",
                    "alerts_created_during_day",
                    "ending_low_severity_alerts",
                    "ending_medium_severity_alerts",
                    "ending_high_severity_alerts",
                    "ending_critical_severity_alerts",
                ),
            )
        )

        metrics.update(
            self._row_to_metrics(
                risk_row,
                (
                    "ending_low_risk_customers",
                    "ending_medium_risk_customers",
                    "ending_high_risk_customers",
                    "ending_critical_risk_customers",
                ),
            )
        )

        return metrics

    def collect_operations_metrics(
        self,
        *,
        as_of: datetime,
    ) -> dict[str, int]:
        """Collect task and workflow state and day-to-date activity."""

        day_start = self._day_start(as_of)

        open_task_statuses = (
            TaskStatus.NEW,
            TaskStatus.ASSIGNED,
            TaskStatus.IN_PROGRESS,
        )

        task_statement = select(
            func.count(Task.id).label(
                "ending_total_tasks",
            ),
            self._count_filter(
                Task,
                Task.created_at >= day_start,
                Task.created_at <= as_of,
            ).label(
                "tasks_created_during_day",
            ),
            func.count(Task.id)
            .filter(
                Task.status.in_(open_task_statuses),
            )
            .label(
                "ending_open_tasks",
            ),
            func.count(Task.id)
            .filter(
                Task.status == TaskStatus.COMPLETED,
            )
            .label(
                "ending_total_completed_tasks",
            ),
            self._count_filter(
                Task,
                Task.completed_at >= day_start,
                Task.completed_at <= as_of,
                Task.status == TaskStatus.COMPLETED,
            ).label(
                "tasks_completed_during_day",
            ),
            func.count(Task.id)
            .filter(
                Task.status.in_(open_task_statuses),
                Task.due_date.is_not(None),
                Task.due_date < as_of,
            )
            .label(
                "ending_overdue_tasks",
            ),
            func.count(Task.id)
            .filter(
                Task.sla_status == SLAStatus.WITHIN_SLA,
            )
            .label(
                "ending_tasks_sla_within_target",
            ),
            func.count(Task.id)
            .filter(
                Task.sla_status == SLAStatus.APPROACHING_DEADLINE,
            )
            .label(
                "ending_tasks_sla_approaching_deadline",
            ),
            func.count(Task.id)
            .filter(
                Task.sla_status == SLAStatus.BREACHED,
            )
            .label(
                "ending_tasks_sla_breached",
            ),
            func.count(Task.id)
            .filter(
                Task.sla_status == SLAStatus.COMPLETED,
            )
            .label(
                "ending_tasks_sla_completed_on_time",
            ),
            self._count_filter(
                Task,
                Task.completed_at >= day_start,
                Task.completed_at <= as_of,
                Task.status == TaskStatus.COMPLETED,
                Task.sla_status == SLAStatus.COMPLETED,
            ).label(
                "tasks_completed_within_sla_during_day",
            ),
            self._count_filter(
                Task,
                Task.completed_at >= day_start,
                Task.completed_at <= as_of,
                Task.status == TaskStatus.COMPLETED,
                Task.sla_status == SLAStatus.BREACHED,
            ).label(
                "tasks_completed_breached_sla_during_day",
            ),
        ).where(
            Task.created_at <= as_of,
        )

        task_row = self.db.execute(task_statement).one()

        workflow_statement = select(
            func.count(
                WorkflowExecution.id,
            ).label(
                "ending_total_workflows",
            ),
            self._count_filter(
                WorkflowExecution,
                WorkflowExecution.started_at >= day_start,
                WorkflowExecution.started_at <= as_of,
            ).label(
                "workflows_started_during_day",
            ),
            func.count(
                WorkflowExecution.id,
            )
            .filter(
                WorkflowExecution.status == WorkflowExecutionStatus.IN_PROGRESS,
            )
            .label(
                "ending_active_workflows",
            ),
            func.count(
                WorkflowExecution.id,
            )
            .filter(
                WorkflowExecution.status == WorkflowExecutionStatus.COMPLETED,
            )
            .label(
                "ending_total_completed_workflows",
            ),
            self._count_filter(
                WorkflowExecution,
                WorkflowExecution.completed_at >= day_start,
                WorkflowExecution.completed_at <= as_of,
                WorkflowExecution.status == WorkflowExecutionStatus.COMPLETED,
            ).label(
                "workflows_completed_during_day",
            ),
            func.count(
                WorkflowExecution.id,
            )
            .filter(
                WorkflowExecution.status == WorkflowExecutionStatus.FAILED,
            )
            .label(
                "ending_total_failed_workflows",
            ),
            self._count_filter(
                WorkflowExecution,
                WorkflowExecution.completed_at >= day_start,
                WorkflowExecution.completed_at <= as_of,
                WorkflowExecution.status == WorkflowExecutionStatus.FAILED,
            ).label(
                "workflows_failed_during_day",
            ),
            func.count(
                WorkflowExecution.id,
            )
            .filter(
                WorkflowExecution.sla_status == SLAStatus.WITHIN_SLA,
            )
            .label(
                "ending_workflows_sla_within_target",
            ),
            func.count(
                WorkflowExecution.id,
            )
            .filter(
                WorkflowExecution.sla_status == SLAStatus.APPROACHING_DEADLINE,
            )
            .label(
                "ending_workflows_sla_approaching_deadline",
            ),
            func.count(
                WorkflowExecution.id,
            )
            .filter(
                WorkflowExecution.sla_status == SLAStatus.BREACHED,
            )
            .label(
                "ending_workflows_sla_breached",
            ),
            func.count(
                WorkflowExecution.id,
            )
            .filter(
                WorkflowExecution.sla_status == SLAStatus.COMPLETED,
            )
            .label(
                "ending_workflows_sla_completed_on_time",
            ),
            self._count_filter(
                WorkflowExecution,
                WorkflowExecution.completed_at >= day_start,
                WorkflowExecution.completed_at <= as_of,
                WorkflowExecution.status == WorkflowExecutionStatus.COMPLETED,
                WorkflowExecution.sla_status == SLAStatus.COMPLETED,
            ).label(
                "workflows_completed_within_sla_during_day",
            ),
            self._count_filter(
                WorkflowExecution,
                WorkflowExecution.completed_at >= day_start,
                WorkflowExecution.completed_at <= as_of,
                WorkflowExecution.status == WorkflowExecutionStatus.COMPLETED,
                WorkflowExecution.sla_status == SLAStatus.BREACHED,
            ).label(
                "workflows_completed_breached_sla_during_day",
            ),
        ).where(
            WorkflowExecution.started_at <= as_of,
        )

        workflow_row = self.db.execute(workflow_statement).one()

        metrics = self._row_to_metrics(
            task_row,
            (
                "ending_total_tasks",
                "tasks_created_during_day",
                "ending_open_tasks",
                "ending_total_completed_tasks",
                "tasks_completed_during_day",
                "ending_overdue_tasks",
                "ending_tasks_sla_within_target",
                "ending_tasks_sla_approaching_deadline",
                "ending_tasks_sla_breached",
                "ending_tasks_sla_completed_on_time",
                "tasks_completed_within_sla_during_day",
                "tasks_completed_breached_sla_during_day",
            ),
        )

        metrics.update(
            self._row_to_metrics(
                workflow_row,
                (
                    "ending_total_workflows",
                    "workflows_started_during_day",
                    "ending_active_workflows",
                    "ending_total_completed_workflows",
                    "workflows_completed_during_day",
                    "ending_total_failed_workflows",
                    "workflows_failed_during_day",
                    "ending_workflows_sla_within_target",
                    "ending_workflows_sla_approaching_deadline",
                    "ending_workflows_sla_breached",
                    "ending_workflows_sla_completed_on_time",
                    "workflows_completed_within_sla_during_day",
                    "workflows_completed_breached_sla_during_day",
                ),
            )
        )

        return metrics

    def _save_snapshot(
        self,
        *,
        model: Any,
        snapshot_date: date,
        captured_at: datetime,
        metrics: dict[str, int],
        fields: tuple[str, ...],
    ) -> Any:
        snapshot = self.db.get(
            model,
            snapshot_date,
        )

        if snapshot is None:
            snapshot = model(
                snapshot_date=snapshot_date,
            )
            self.db.add(snapshot)

        for field in fields:
            setattr(
                snapshot,
                field,
                int(metrics.get(field, 0) or 0),
            )

        snapshot.captured_at = captured_at

        self.db.flush()

        return snapshot

    def save_customer_snapshot(
        self,
        *,
        snapshot_date: date,
        captured_at: datetime,
        metrics: dict[str, int],
    ) -> Any:
        return self._save_snapshot(
            model=CustomerAnalyticsDaily,
            snapshot_date=snapshot_date,
            captured_at=captured_at,
            metrics=metrics,
            fields=self.CUSTOMER_FIELDS,
        )

    def save_compliance_snapshot(
        self,
        *,
        snapshot_date: date,
        captured_at: datetime,
        metrics: dict[str, int],
    ) -> Any:
        return self._save_snapshot(
            model=ComplianceAnalyticsDaily,
            snapshot_date=snapshot_date,
            captured_at=captured_at,
            metrics=metrics,
            fields=self.COMPLIANCE_FIELDS,
        )

    def save_operations_snapshot(
        self,
        *,
        snapshot_date: date,
        captured_at: datetime,
        metrics: dict[str, int],
    ) -> Any:
        return self._save_snapshot(
            model=OperationsAnalyticsDaily,
            snapshot_date=snapshot_date,
            captured_at=captured_at,
            metrics=metrics,
            fields=self.OPERATIONS_FIELDS,
        )
