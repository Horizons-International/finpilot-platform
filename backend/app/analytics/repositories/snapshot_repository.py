from datetime import date, datetime

from sqlalchemy import case, func, select
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
from app.models.workflow import WorkflowExecution
from app.utils.enums import (
    ComplianceCaseStatus,
    CustomerRiskLevel,
    CustomerStatus,
    SLAStatus,
    TaskStatus,
    TransactionMonitoringOutcome,
    WorkflowExecutionStatus,
)


class AnalyticsSnapshotRepository:
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

    def collect_customer_metrics(
        self,
        *,
        as_of: datetime,
    ) -> dict[str, int]:
        day_start = self._day_start(as_of)

        statement = select(
            func.count(Customer.id).label("total_customers"),
            func.sum(
                case(
                    (
                        Customer.created_at >= day_start,
                        1,
                    ),
                    else_=0,
                )
            ).label("new_registrations"),
            func.sum(
                case(
                    (
                        Customer.status == CustomerStatus.PENDING_VERIFICATION,
                        1,
                    ),
                    else_=0,
                )
            ).label("pending_verification"),
            func.sum(
                case(
                    (
                        Customer.status == CustomerStatus.VERIFIED,
                        1,
                    ),
                    else_=0,
                )
            ).label("verified_customers"),
            func.sum(
                case(
                    (
                        Customer.status == CustomerStatus.SUSPENDED,
                        1,
                    ),
                    else_=0,
                )
            ).label("suspended_customers"),
            func.sum(
                case(
                    (
                        Customer.status == CustomerStatus.REJECTED,
                        1,
                    ),
                    else_=0,
                )
            ).label("rejected_customers"),
        ).where(
            Customer.created_at <= as_of,
        )

        row = self.db.execute(statement).one()

        return {
            "total_customers": int(row.total_customers or 0),
            "new_registrations": int(row.new_registrations or 0),
            "pending_verification": int(row.pending_verification or 0),
            "verified_customers": int(row.verified_customers or 0),
            "suspended_customers": int(row.suspended_customers or 0),
            "rejected_customers": int(row.rejected_customers or 0),
        }

    def collect_compliance_metrics(
        self,
        *,
        as_of: datetime,
    ) -> dict[str, int]:
        open_statuses = (
            ComplianceCaseStatus.OPEN,
            ComplianceCaseStatus.ASSIGNED,
            ComplianceCaseStatus.UNDER_REVIEW,
            ComplianceCaseStatus.ESCALATED,
        )

        case_statement = select(
            func.count(ComplianceCase.id).label("total_cases"),
            func.sum(
                case(
                    (
                        ComplianceCase.status.in_(open_statuses),
                        1,
                    ),
                    else_=0,
                )
            ).label("open_cases"),
            func.sum(
                case(
                    (
                        ComplianceCase.status == ComplianceCaseStatus.RESOLVED,
                        1,
                    ),
                    else_=0,
                )
            ).label("resolved_cases"),
            func.sum(
                case(
                    (
                        ComplianceCase.status == ComplianceCaseStatus.CLOSED,
                        1,
                    ),
                    else_=0,
                )
            ).label("closed_cases"),
        ).where(
            ComplianceCase.created_at <= as_of,
        )

        case_row = self.db.execute(case_statement).one()

        alert_statement = (
            select(
                func.count(TransactionMonitoringResult.id).label("total_alerts"),
                func.sum(
                    case(
                        (
                            AMLRule.severity == "LOW",
                            1,
                        ),
                        else_=0,
                    )
                ).label("low_severity_alerts"),
                func.sum(
                    case(
                        (
                            AMLRule.severity == "MEDIUM",
                            1,
                        ),
                        else_=0,
                    )
                ).label("medium_severity_alerts"),
                func.sum(
                    case(
                        (
                            AMLRule.severity == "HIGH",
                            1,
                        ),
                        else_=0,
                    )
                ).label("high_severity_alerts"),
                func.sum(
                    case(
                        (
                            AMLRule.severity == "CRITICAL",
                            1,
                        ),
                        else_=0,
                    )
                ).label("critical_severity_alerts"),
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
            func.sum(
                case(
                    (
                        CustomerRiskProfile.risk_level == CustomerRiskLevel.LOW,
                        1,
                    ),
                    else_=0,
                )
            ).label("low_risk_customers"),
            func.sum(
                case(
                    (
                        CustomerRiskProfile.risk_level == CustomerRiskLevel.MEDIUM,
                        1,
                    ),
                    else_=0,
                )
            ).label("medium_risk_customers"),
            func.sum(
                case(
                    (
                        CustomerRiskProfile.risk_level == CustomerRiskLevel.HIGH,
                        1,
                    ),
                    else_=0,
                )
            ).label("high_risk_customers"),
            func.sum(
                case(
                    (
                        CustomerRiskProfile.risk_level == CustomerRiskLevel.CRITICAL,
                        1,
                    ),
                    else_=0,
                )
            ).label("critical_risk_customers"),
        ).where(
            CustomerRiskProfile.assessed_at <= as_of,
        )

        risk_row = self.db.execute(risk_statement).one()

        return {
            "total_cases": int(case_row.total_cases or 0),
            "open_cases": int(case_row.open_cases or 0),
            "resolved_cases": int(case_row.resolved_cases or 0),
            "closed_cases": int(case_row.closed_cases or 0),
            "total_alerts": int(alert_row.total_alerts or 0),
            "low_severity_alerts": int(alert_row.low_severity_alerts or 0),
            "medium_severity_alerts": int(alert_row.medium_severity_alerts or 0),
            "high_severity_alerts": int(alert_row.high_severity_alerts or 0),
            "critical_severity_alerts": int(alert_row.critical_severity_alerts or 0),
            "low_risk_customers": int(risk_row.low_risk_customers or 0),
            "medium_risk_customers": int(risk_row.medium_risk_customers or 0),
            "high_risk_customers": int(risk_row.high_risk_customers or 0),
            "critical_risk_customers": int(risk_row.critical_risk_customers or 0),
        }

    def collect_operations_metrics(
        self,
        *,
        as_of: datetime,
    ) -> dict[str, int]:
        open_task_statuses = (
            TaskStatus.NEW,
            TaskStatus.ASSIGNED,
            TaskStatus.IN_PROGRESS,
        )

        task_statement = select(
            func.count(Task.id).label("total_tasks"),
            func.sum(
                case(
                    (
                        Task.status.in_(open_task_statuses),
                        1,
                    ),
                    else_=0,
                )
            ).label("open_tasks"),
            func.sum(
                case(
                    (
                        Task.status == TaskStatus.COMPLETED,
                        1,
                    ),
                    else_=0,
                )
            ).label("completed_tasks"),
            func.sum(
                case(
                    (
                        Task.status.in_(open_task_statuses)
                        & Task.due_date.is_not(None)
                        & (Task.due_date < as_of),
                        1,
                    ),
                    else_=0,
                )
            ).label("overdue_tasks"),
            func.sum(
                case(
                    (
                        Task.sla_status == SLAStatus.WITHIN_SLA,
                        1,
                    ),
                    else_=0,
                )
            ).label("task_sla_within_sla"),
            func.sum(
                case(
                    (
                        Task.sla_status == SLAStatus.APPROACHING_DEADLINE,
                        1,
                    ),
                    else_=0,
                )
            ).label("task_sla_approaching_deadline"),
            func.sum(
                case(
                    (
                        Task.sla_status == SLAStatus.BREACHED,
                        1,
                    ),
                    else_=0,
                )
            ).label("task_sla_breached"),
            func.sum(
                case(
                    (
                        Task.sla_status == SLAStatus.COMPLETED,
                        1,
                    ),
                    else_=0,
                )
            ).label("task_sla_completed"),
        ).where(
            Task.created_at <= as_of,
        )

        task_row = self.db.execute(task_statement).one()

        workflow_statement = select(
            func.count(WorkflowExecution.id).label("total_workflows"),
            func.sum(
                case(
                    (
                        WorkflowExecution.status == WorkflowExecutionStatus.IN_PROGRESS,
                        1,
                    ),
                    else_=0,
                )
            ).label("active_workflows"),
            func.sum(
                case(
                    (
                        WorkflowExecution.status == WorkflowExecutionStatus.COMPLETED,
                        1,
                    ),
                    else_=0,
                )
            ).label("completed_workflows"),
            func.sum(
                case(
                    (
                        WorkflowExecution.status == WorkflowExecutionStatus.FAILED,
                        1,
                    ),
                    else_=0,
                )
            ).label("failed_workflows"),
            func.sum(
                case(
                    (
                        WorkflowExecution.sla_status == SLAStatus.WITHIN_SLA,
                        1,
                    ),
                    else_=0,
                )
            ).label("workflow_sla_within_sla"),
            func.sum(
                case(
                    (
                        WorkflowExecution.sla_status == SLAStatus.APPROACHING_DEADLINE,
                        1,
                    ),
                    else_=0,
                )
            ).label("workflow_sla_approaching_deadline"),
            func.sum(
                case(
                    (
                        WorkflowExecution.sla_status == SLAStatus.BREACHED,
                        1,
                    ),
                    else_=0,
                )
            ).label("workflow_sla_breached"),
            func.sum(
                case(
                    (
                        WorkflowExecution.sla_status == SLAStatus.COMPLETED,
                        1,
                    ),
                    else_=0,
                )
            ).label("workflow_sla_completed"),
        ).where(
            WorkflowExecution.started_at <= as_of,
        )

        workflow_row = self.db.execute(workflow_statement).one()

        return {
            "total_tasks": int(task_row.total_tasks or 0),
            "open_tasks": int(task_row.open_tasks or 0),
            "completed_tasks": int(task_row.completed_tasks or 0),
            "overdue_tasks": int(task_row.overdue_tasks or 0),
            "task_sla_within_sla": int(task_row.task_sla_within_sla or 0),
            "task_sla_approaching_deadline": int(
                task_row.task_sla_approaching_deadline or 0
            ),
            "task_sla_breached": int(task_row.task_sla_breached or 0),
            "task_sla_completed": int(task_row.task_sla_completed or 0),
            "total_workflows": int(workflow_row.total_workflows or 0),
            "active_workflows": int(workflow_row.active_workflows or 0),
            "completed_workflows": int(workflow_row.completed_workflows or 0),
            "failed_workflows": int(workflow_row.failed_workflows or 0),
            "workflow_sla_within_sla": int(workflow_row.workflow_sla_within_sla or 0),
            "workflow_sla_approaching_deadline": int(
                workflow_row.workflow_sla_approaching_deadline or 0
            ),
            "workflow_sla_breached": int(workflow_row.workflow_sla_breached or 0),
            "workflow_sla_completed": int(workflow_row.workflow_sla_completed or 0),
        }

    def save_customer_snapshot(
        self,
        *,
        snapshot_date: date,
        captured_at: datetime,
        metrics: dict[str, int],
    ) -> CustomerAnalyticsDaily:
        snapshot = self.db.get(
            CustomerAnalyticsDaily,
            snapshot_date,
        )

        if snapshot is None:
            snapshot = CustomerAnalyticsDaily(
                snapshot_date=snapshot_date,
            )
            self.db.add(snapshot)

        snapshot.total_customers = metrics["total_customers"]
        snapshot.new_registrations = metrics["new_registrations"]
        snapshot.pending_verification = metrics["pending_verification"]
        snapshot.verified_customers = metrics["verified_customers"]
        snapshot.suspended_customers = metrics["suspended_customers"]
        snapshot.rejected_customers = metrics["rejected_customers"]
        snapshot.captured_at = captured_at

        self.db.flush()

        return snapshot

    def save_compliance_snapshot(
        self,
        *,
        snapshot_date: date,
        captured_at: datetime,
        metrics: dict[str, int],
    ) -> ComplianceAnalyticsDaily:
        snapshot = self.db.get(
            ComplianceAnalyticsDaily,
            snapshot_date,
        )

        if snapshot is None:
            snapshot = ComplianceAnalyticsDaily(
                snapshot_date=snapshot_date,
            )
            self.db.add(snapshot)

        for field in (
            "total_cases",
            "open_cases",
            "resolved_cases",
            "closed_cases",
            "total_alerts",
            "low_severity_alerts",
            "medium_severity_alerts",
            "high_severity_alerts",
            "critical_severity_alerts",
            "low_risk_customers",
            "medium_risk_customers",
            "high_risk_customers",
            "critical_risk_customers",
        ):
            setattr(snapshot, field, metrics[field])

        snapshot.captured_at = captured_at

        self.db.flush()

        return snapshot

    def save_operations_snapshot(
        self,
        *,
        snapshot_date: date,
        captured_at: datetime,
        metrics: dict[str, int],
    ) -> OperationsAnalyticsDaily:
        snapshot = self.db.get(
            OperationsAnalyticsDaily,
            snapshot_date,
        )

        if snapshot is None:
            snapshot = OperationsAnalyticsDaily(
                snapshot_date=snapshot_date,
            )
            self.db.add(snapshot)

        for field in (
            "total_tasks",
            "open_tasks",
            "completed_tasks",
            "overdue_tasks",
            "task_sla_within_sla",
            "task_sla_approaching_deadline",
            "task_sla_breached",
            "task_sla_completed",
            "total_workflows",
            "active_workflows",
            "completed_workflows",
            "failed_workflows",
            "workflow_sla_within_sla",
            "workflow_sla_approaching_deadline",
            "workflow_sla_breached",
            "workflow_sla_completed",
        ):
            setattr(snapshot, field, metrics[field])

        snapshot.captured_at = captured_at

        self.db.flush()

        return snapshot
