from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.analytics.metrics.engine import MetricEngine
from app.analytics.metrics.measure_provider import MetricMeasureProvider
from app.analytics.repositories.compliance_analytics_repository import (
    ComplianceAnalyticsRepository,
)
from app.analytics.repositories.customer_analytics_repository import (
    CustomerAnalyticsRepository,
)
from app.analytics.repositories.metric_repository import MetricRepository
from app.analytics.repositories.operations_analytics_repository import (
    OperationsAnalyticsRepository,
)
from app.schemas.ai_analytics_assistant import (
    AnalyticsEvidence,
    AnalyticsQuestionPlan,
    AnalyticsQuestionType,
)
from app.utils.enums import (
    MetricStatus,
    MetricValueType,
)
from app.utils.errors import bad_request


@dataclass(frozen=True)
class AnalyticsDataBundle:
    context: dict[str, Any]
    supporting_data: list[AnalyticsEvidence]


class AnalyticsAssistantDataService:
    def __init__(
        self,
        db: Session,
    ) -> None:
        self.customer_repository = CustomerAnalyticsRepository(db)
        self.compliance_repository = ComplianceAnalyticsRepository(db)
        self.operations_repository = OperationsAnalyticsRepository(db)

        self.metric_repository = MetricRepository(db)
        self.metric_engine = MetricEngine(
            MetricMeasureProvider(db),
        )

    @staticmethod
    def _percentage_change(
        current: float | int | None,
        previous: float | int | None,
    ) -> float | None:
        if current is None or previous is None:
            return None

        previous_value = float(previous)

        if previous_value == 0:
            return None

        return round(
            ((float(current) - previous_value) / abs(previous_value)) * 100,
            2,
        )

    @staticmethod
    def _sum_customer_registrations(
        rows,
    ) -> int:
        return sum(int(row.customers_registered_during_day or 0) for row in rows)

    @staticmethod
    def _sum_alerts_created(
        rows,
    ) -> int:
        return sum(int(row.alerts_created_during_day or 0) for row in rows)

    @staticmethod
    def _sum_cases_created(
        rows,
    ) -> int:
        return sum(int(row.cases_created_during_day or 0) for row in rows)

    @staticmethod
    def _sum_tasks_completed(
        rows,
    ) -> int:
        return sum(int(row.tasks_completed_during_day or 0) for row in rows)

    @staticmethod
    def _sum_tasks_within_sla(
        rows,
    ) -> int:
        return sum(int(row.tasks_completed_within_sla_during_day or 0) for row in rows)

    @staticmethod
    def _sum_tasks_breached_sla(
        rows,
    ) -> int:
        return sum(
            int(row.tasks_completed_breached_sla_during_day or 0) for row in rows
        )

    @staticmethod
    def _sum_workflows_started(
        rows,
    ) -> int:
        return sum(int(row.workflows_started_during_day or 0) for row in rows)

    @staticmethod
    def _sum_workflows_completed(
        rows,
    ) -> int:
        return sum(int(row.workflows_completed_during_day or 0) for row in rows)

    @staticmethod
    def _sum_workflows_failed(
        rows,
    ) -> int:
        return sum(int(row.workflows_failed_during_day or 0) for row in rows)

    def get_data(
        self,
        plan: AnalyticsQuestionPlan,
    ) -> AnalyticsDataBundle:
        if plan.question_type == AnalyticsQuestionType.CONFIGURED_METRIC:
            return self._configured_metric(plan)

        if plan.question_type == AnalyticsQuestionType.PENDING_VERIFICATION:
            return self._pending_verification(plan)

        if plan.question_type == AnalyticsQuestionType.VERIFICATION_REJECTION_REASONS:
            return self._verification_rejection_reasons(plan)

        if plan.question_type == AnalyticsQuestionType.CUSTOMER_REGISTRATIONS:
            return self._customer_registrations(plan)

        if plan.question_type == AnalyticsQuestionType.RISK_DISTRIBUTION:
            return self._risk_distribution(plan)

        if plan.question_type == AnalyticsQuestionType.AML_ALERTS:
            return self._aml_alerts(plan)

        if plan.question_type == AnalyticsQuestionType.COMPLIANCE_CASES:
            return self._compliance_cases(plan)

        if plan.question_type == AnalyticsQuestionType.TASK_PERFORMANCE:
            return self._task_performance(plan)

        if plan.question_type == AnalyticsQuestionType.WORKFLOW_PERFORMANCE:
            return self._workflow_performance(plan)

        raise bad_request(
            "Unsupported analytics question type.",
        )

    def _configured_metric(
        self,
        plan: AnalyticsQuestionPlan,
    ) -> AnalyticsDataBundle:
        if plan.metric_key is None:
            raise bad_request(
                "A metric key is required for this analytics question.",
            )

        metric = self.metric_repository.get_definition_by_key(
            plan.metric_key,
        )

        if metric is None or metric.status != MetricStatus.ACTIVE:
            raise bad_request(
                f"Analytics metric '{plan.metric_key}' is unavailable.",
            )

        current_value = self.metric_engine.calculate(
            metric=metric,
            start_date=plan.start_date,
            end_date=plan.end_date,
        )

        comparison_value = self.metric_engine.calculate(
            metric=metric,
            start_date=plan.comparison_start_date,
            end_date=plan.comparison_end_date,
        )

        change_percentage = self._percentage_change(
            current_value,
            comparison_value,
        )

        unit = "%" if metric.value_type == MetricValueType.PERCENTAGE else "seconds"

        evidence = AnalyticsEvidence(
            key=metric.key,
            label=metric.name,
            value=current_value,
            unit=unit,
            source="metric_engine",
            comparison_value=comparison_value,
            comparison_change_percentage=change_percentage,
            details={
                "description": metric.description,
                "period_start": str(plan.start_date),
                "period_end": str(plan.end_date),
                "comparison_start": str(
                    plan.comparison_start_date,
                ),
                "comparison_end": str(
                    plan.comparison_end_date,
                ),
            },
        )

        return AnalyticsDataBundle(
            context={
                "question_type": plan.question_type.value,
                "metric": {
                    "key": metric.key,
                    "name": metric.name,
                    "description": metric.description,
                    "value_type": metric.value_type.value,
                    "definition": metric.definition,
                },
                "period": {
                    "start_date": str(plan.start_date),
                    "end_date": str(plan.end_date),
                    "value": current_value,
                },
                "comparison_period": {
                    "start_date": str(
                        plan.comparison_start_date,
                    ),
                    "end_date": str(
                        plan.comparison_end_date,
                    ),
                    "value": comparison_value,
                },
                "change_percentage": change_percentage,
            },
            supporting_data=[evidence],
        )

    def _pending_verification(
        self,
        plan: AnalyticsQuestionPlan,
    ) -> AnalyticsDataBundle:
        current_snapshot = self.customer_repository.get_latest_snapshot(
            end_date=plan.end_date,
        )

        comparison_snapshot = self.customer_repository.get_latest_snapshot(
            end_date=plan.comparison_end_date,
        )

        current_value = (
            current_snapshot.ending_pending_verification_customers
            if current_snapshot is not None
            else None
        )

        comparison_value = (
            comparison_snapshot.ending_pending_verification_customers
            if comparison_snapshot is not None
            else None
        )

        change_percentage = self._percentage_change(
            current_value,
            comparison_value,
        )

        evidence = AnalyticsEvidence(
            key="pending_verification_customers",
            label="Pending verification customers at period end",
            value=current_value,
            unit="customers",
            source="analytics_customer_daily",
            comparison_value=comparison_value,
            comparison_change_percentage=change_percentage,
            details={
                "current_snapshot_date": (
                    str(current_snapshot.snapshot_date)
                    if current_snapshot is not None
                    else None
                ),
                "comparison_snapshot_date": (
                    str(comparison_snapshot.snapshot_date)
                    if comparison_snapshot is not None
                    else None
                ),
            },
        )

        return AnalyticsDataBundle(
            context={
                "question_type": plan.question_type.value,
                "period": {
                    "start_date": str(plan.start_date),
                    "end_date": str(plan.end_date),
                    "pending_verification_customers": current_value,
                },
                "comparison_period": {
                    "start_date": str(
                        plan.comparison_start_date,
                    ),
                    "end_date": str(
                        plan.comparison_end_date,
                    ),
                    "pending_verification_customers": comparison_value,
                },
                "change_percentage": change_percentage,
            },
            supporting_data=[evidence],
        )

    def _verification_rejection_reasons(
        self,
        plan: AnalyticsQuestionPlan,
    ) -> AnalyticsDataBundle:
        current_reasons = self.compliance_repository.get_verification_rejection_reasons(
            start_date=plan.start_date,
            end_date=plan.end_date,
        )

        comparison_reasons = (
            self.compliance_repository.get_verification_rejection_reasons(
                start_date=plan.comparison_start_date,
                end_date=plan.comparison_end_date,
            )
        )

        current_total = sum(count for _, count in current_reasons)

        if not current_reasons:
            top_reason_name = None
            top_reason_count = 0
            top_reason_share = None
            comparison_count = None
            change_percentage = None

        else:
            top_reason_name, top_reason_count = current_reasons[0]

            top_reason_share = (
                round(
                    (top_reason_count / current_total) * 100,
                    2,
                )
                if current_total > 0
                else None
            )

            comparison_count = dict(
                comparison_reasons,
            ).get(
                top_reason_name,
            )

            change_percentage = self._percentage_change(
                top_reason_count,
                comparison_count,
            )

        evidence = AnalyticsEvidence(
            key="top_verification_rejection_reason",
            label="Top verification rejection reason",
            value=top_reason_name,
            source="verification_reviews",
            comparison_value=(comparison_count if top_reason_name else None),
            comparison_change_percentage=change_percentage,
            details={
                "count": top_reason_count,
                "share_percentage": top_reason_share,
                "top_reasons": [
                    {
                        "reason": reason,
                        "count": count,
                    }
                    for reason, count in current_reasons[:5]
                ],
                "total_rejections": current_total,
            },
        )

        return AnalyticsDataBundle(
            context={
                "question_type": plan.question_type.value,
                "period": {
                    "start_date": str(plan.start_date),
                    "end_date": str(plan.end_date),
                    "total_rejections": current_total,
                    "top_reason": top_reason_name,
                    "top_reason_count": top_reason_count,
                    "top_reasons": [
                        {
                            "reason": reason,
                            "count": count,
                        }
                        for reason, count in current_reasons[:10]
                    ],
                },
                "comparison_period": {
                    "start_date": str(
                        plan.comparison_start_date,
                    ),
                    "end_date": str(
                        plan.comparison_end_date,
                    ),
                    "top_reasons": [
                        {
                            "reason": reason,
                            "count": count,
                        }
                        for reason, count in comparison_reasons[:10]
                    ],
                },
            },
            supporting_data=[evidence],
        )

    def _customer_registrations(
        self,
        plan: AnalyticsQuestionPlan,
    ) -> AnalyticsDataBundle:
        current_rows = self.customer_repository.get_daily_snapshots(
            start_date=plan.start_date,
            end_date=plan.end_date,
        )

        comparison_rows = self.customer_repository.get_daily_snapshots(
            start_date=plan.comparison_start_date,
            end_date=plan.comparison_end_date,
        )

        current_value = self._sum_customer_registrations(
            current_rows,
        )

        comparison_value = self._sum_customer_registrations(
            comparison_rows,
        )

        change_percentage = self._percentage_change(
            current_value,
            comparison_value,
        )

        evidence = AnalyticsEvidence(
            key="customers_registered_during_period",
            label="Customers registered during period",
            value=current_value,
            unit="customers",
            source="analytics_customer_daily",
            comparison_value=comparison_value,
            comparison_change_percentage=change_percentage,
        )

        return AnalyticsDataBundle(
            context={
                "question_type": plan.question_type.value,
                "period": {
                    "start_date": str(plan.start_date),
                    "end_date": str(plan.end_date),
                    "customers_registered": current_value,
                },
                "comparison_period": {
                    "start_date": str(
                        plan.comparison_start_date,
                    ),
                    "end_date": str(
                        plan.comparison_end_date,
                    ),
                    "customers_registered": comparison_value,
                },
                "change_percentage": change_percentage,
            },
            supporting_data=[evidence],
        )

    def _risk_distribution(
        self,
        plan: AnalyticsQuestionPlan,
    ) -> AnalyticsDataBundle:
        current_snapshot = self.compliance_repository.get_latest_snapshot(
            end_date=plan.end_date,
        )

        comparison_snapshot = self.compliance_repository.get_latest_snapshot(
            end_date=plan.comparison_end_date,
        )

        risk_values = {
            "LOW": (
                current_snapshot.ending_low_risk_customers if current_snapshot else 0
            ),
            "MEDIUM": (
                current_snapshot.ending_medium_risk_customers if current_snapshot else 0
            ),
            "HIGH": (
                current_snapshot.ending_high_risk_customers if current_snapshot else 0
            ),
            "CRITICAL": (
                current_snapshot.ending_critical_risk_customers
                if current_snapshot
                else 0
            ),
        }

        comparison_values = {
            "LOW": (
                comparison_snapshot.ending_low_risk_customers
                if comparison_snapshot
                else 0
            ),
            "MEDIUM": (
                comparison_snapshot.ending_medium_risk_customers
                if comparison_snapshot
                else 0
            ),
            "HIGH": (
                comparison_snapshot.ending_high_risk_customers
                if comparison_snapshot
                else 0
            ),
            "CRITICAL": (
                comparison_snapshot.ending_critical_risk_customers
                if comparison_snapshot
                else 0
            ),
        }

        evidence = [
            AnalyticsEvidence(
                key=f"risk_{level.lower()}_customers",
                label=f"{level.title()} risk customers",
                value=current_value,
                unit="customers",
                source="analytics_compliance_daily",
                comparison_value=comparison_values[level],
                comparison_change_percentage=self._percentage_change(
                    current_value,
                    comparison_values[level],
                ),
            )
            for level, current_value in risk_values.items()
        ]

        return AnalyticsDataBundle(
            context={
                "question_type": plan.question_type.value,
                "period": {
                    "start_date": str(plan.start_date),
                    "end_date": str(plan.end_date),
                    "risk_distribution": risk_values,
                },
                "comparison_period": {
                    "start_date": str(
                        plan.comparison_start_date,
                    ),
                    "end_date": str(
                        plan.comparison_end_date,
                    ),
                    "risk_distribution": comparison_values,
                },
            },
            supporting_data=evidence,
        )

    def _aml_alerts(
        self,
        plan: AnalyticsQuestionPlan,
    ) -> AnalyticsDataBundle:
        current_rows = self.compliance_repository.get_daily_snapshots(
            start_date=plan.start_date,
            end_date=plan.end_date,
        )

        comparison_rows = self.compliance_repository.get_daily_snapshots(
            start_date=plan.comparison_start_date,
            end_date=plan.comparison_end_date,
        )

        current_created = self._sum_alerts_created(
            current_rows,
        )

        comparison_created = self._sum_alerts_created(
            comparison_rows,
        )

        current_snapshot = self.compliance_repository.get_latest_snapshot(
            end_date=plan.end_date,
        )

        comparison_snapshot = self.compliance_repository.get_latest_snapshot(
            end_date=plan.comparison_end_date,
        )

        current_ending_total = (
            current_snapshot.ending_total_alerts if current_snapshot else 0
        )

        comparison_ending_total = (
            comparison_snapshot.ending_total_alerts if comparison_snapshot else 0
        )

        return AnalyticsDataBundle(
            context={
                "question_type": plan.question_type.value,
                "period": {
                    "start_date": str(plan.start_date),
                    "end_date": str(plan.end_date),
                    "alerts_created": current_created,
                    "ending_total_alerts": current_ending_total,
                },
                "comparison_period": {
                    "start_date": str(
                        plan.comparison_start_date,
                    ),
                    "end_date": str(
                        plan.comparison_end_date,
                    ),
                    "alerts_created": comparison_created,
                    "ending_total_alerts": comparison_ending_total,
                },
            },
            supporting_data=[
                AnalyticsEvidence(
                    key="alerts_created_during_period",
                    label="AML alerts created during period",
                    value=current_created,
                    unit="alerts",
                    source="analytics_compliance_daily",
                    comparison_value=comparison_created,
                    comparison_change_percentage=self._percentage_change(
                        current_created,
                        comparison_created,
                    ),
                ),
                AnalyticsEvidence(
                    key="ending_total_alerts",
                    label="Total AML alerts at period end",
                    value=current_ending_total,
                    unit="alerts",
                    source="analytics_compliance_daily",
                    comparison_value=comparison_ending_total,
                    comparison_change_percentage=self._percentage_change(
                        current_ending_total,
                        comparison_ending_total,
                    ),
                ),
            ],
        )

    def _compliance_cases(
        self,
        plan: AnalyticsQuestionPlan,
    ) -> AnalyticsDataBundle:
        current_rows = self.compliance_repository.get_daily_snapshots(
            start_date=plan.start_date,
            end_date=plan.end_date,
        )

        comparison_rows = self.compliance_repository.get_daily_snapshots(
            start_date=plan.comparison_start_date,
            end_date=plan.comparison_end_date,
        )

        current_created = self._sum_cases_created(
            current_rows,
        )

        comparison_created = self._sum_cases_created(
            comparison_rows,
        )

        current_snapshot = self.compliance_repository.get_latest_snapshot(
            end_date=plan.end_date,
        )

        comparison_snapshot = self.compliance_repository.get_latest_snapshot(
            end_date=plan.comparison_end_date,
        )

        current_open = current_snapshot.ending_open_cases if current_snapshot else 0

        comparison_open = (
            comparison_snapshot.ending_open_cases if comparison_snapshot else 0
        )

        current_closed = current_snapshot.ending_closed_cases if current_snapshot else 0

        comparison_closed = (
            comparison_snapshot.ending_closed_cases if comparison_snapshot else 0
        )

        return AnalyticsDataBundle(
            context={
                "question_type": plan.question_type.value,
                "period": {
                    "start_date": str(plan.start_date),
                    "end_date": str(plan.end_date),
                    "cases_created": current_created,
                    "ending_open_cases": current_open,
                    "ending_closed_cases": current_closed,
                },
                "comparison_period": {
                    "start_date": str(
                        plan.comparison_start_date,
                    ),
                    "end_date": str(
                        plan.comparison_end_date,
                    ),
                    "cases_created": comparison_created,
                    "ending_open_cases": comparison_open,
                    "ending_closed_cases": comparison_closed,
                },
            },
            supporting_data=[
                AnalyticsEvidence(
                    key="cases_created_during_period",
                    label="Compliance cases created during period",
                    value=current_created,
                    unit="cases",
                    source="analytics_compliance_daily",
                    comparison_value=comparison_created,
                    comparison_change_percentage=self._percentage_change(
                        current_created,
                        comparison_created,
                    ),
                ),
                AnalyticsEvidence(
                    key="ending_open_cases",
                    label="Open compliance cases at period end",
                    value=current_open,
                    unit="cases",
                    source="analytics_compliance_daily",
                    comparison_value=comparison_open,
                    comparison_change_percentage=self._percentage_change(
                        current_open,
                        comparison_open,
                    ),
                ),
                AnalyticsEvidence(
                    key="ending_closed_cases",
                    label="Closed compliance cases at period end",
                    value=current_closed,
                    unit="cases",
                    source="analytics_compliance_daily",
                    comparison_value=comparison_closed,
                    comparison_change_percentage=self._percentage_change(
                        current_closed,
                        comparison_closed,
                    ),
                ),
            ],
        )

    def _task_performance(
        self,
        plan: AnalyticsQuestionPlan,
    ) -> AnalyticsDataBundle:
        current_rows = self.operations_repository.get_daily_snapshots(
            start_date=plan.start_date,
            end_date=plan.end_date,
        )

        comparison_rows = self.operations_repository.get_daily_snapshots(
            start_date=plan.comparison_start_date,
            end_date=plan.comparison_end_date,
        )

        current_completed = self._sum_tasks_completed(
            current_rows,
        )

        comparison_completed = self._sum_tasks_completed(
            comparison_rows,
        )

        current_within = self._sum_tasks_within_sla(
            current_rows,
        )

        current_breached = self._sum_tasks_breached_sla(
            current_rows,
        )

        current_snapshot = self.operations_repository.get_latest_snapshot(
            end_date=plan.end_date,
        )

        ending_open = current_snapshot.ending_open_tasks if current_snapshot else 0

        ending_overdue = (
            current_snapshot.ending_overdue_tasks if current_snapshot else 0
        )

        sla_compliance = (
            round(
                (current_within / current_completed) * 100,
                2,
            )
            if current_completed > 0
            else None
        )

        completed_count, average_resolution_hours = (
            self.operations_repository.get_task_resolution_metrics(
                start_date=plan.start_date,
                end_date=plan.end_date,
            )
        )

        return AnalyticsDataBundle(
            context={
                "question_type": plan.question_type.value,
                "period": {
                    "start_date": str(plan.start_date),
                    "end_date": str(plan.end_date),
                    "tasks_completed": current_completed,
                    "ending_open_tasks": ending_open,
                    "ending_overdue_tasks": ending_overdue,
                    "tasks_completed_within_sla": current_within,
                    "tasks_completed_breached_sla": current_breached,
                    "sla_compliance_percentage": sla_compliance,
                    "average_resolution_time_hours": average_resolution_hours,
                },
                "comparison_period": {
                    "start_date": str(
                        plan.comparison_start_date,
                    ),
                    "end_date": str(
                        plan.comparison_end_date,
                    ),
                    "tasks_completed": comparison_completed,
                },
                "resolution_metric_completed_count": completed_count,
            },
            supporting_data=[
                AnalyticsEvidence(
                    key="tasks_completed_during_period",
                    label="Tasks completed during period",
                    value=current_completed,
                    unit="tasks",
                    source="analytics_operations_daily",
                    comparison_value=comparison_completed,
                    comparison_change_percentage=self._percentage_change(
                        current_completed,
                        comparison_completed,
                    ),
                ),
                AnalyticsEvidence(
                    key="ending_overdue_tasks",
                    label="Overdue tasks at period end",
                    value=ending_overdue,
                    unit="tasks",
                    source="analytics_operations_daily",
                ),
                AnalyticsEvidence(
                    key="task_sla_compliance_percentage",
                    label="Task SLA compliance",
                    value=sla_compliance,
                    unit="%",
                    source="analytics_operations_daily",
                ),
                AnalyticsEvidence(
                    key="average_task_resolution_time_hours",
                    label="Average task resolution time",
                    value=average_resolution_hours,
                    unit="hours",
                    source="tasks",
                ),
            ],
        )

    def _workflow_performance(
        self,
        plan: AnalyticsQuestionPlan,
    ) -> AnalyticsDataBundle:
        current_rows = self.operations_repository.get_daily_snapshots(
            start_date=plan.start_date,
            end_date=plan.end_date,
        )

        comparison_rows = self.operations_repository.get_daily_snapshots(
            start_date=plan.comparison_start_date,
            end_date=plan.comparison_end_date,
        )

        current_started = self._sum_workflows_started(
            current_rows,
        )

        current_completed = self._sum_workflows_completed(
            current_rows,
        )

        current_failed = self._sum_workflows_failed(
            current_rows,
        )

        comparison_completed = self._sum_workflows_completed(
            comparison_rows,
        )

        current_snapshot = self.operations_repository.get_latest_snapshot(
            end_date=plan.end_date,
        )

        ending_active = (
            current_snapshot.ending_active_workflows if current_snapshot else 0
        )

        completed_count, average_completion_hours = (
            self.operations_repository.get_workflow_completion_metrics(
                start_date=plan.start_date,
                end_date=plan.end_date,
            )
        )

        return AnalyticsDataBundle(
            context={
                "question_type": plan.question_type.value,
                "period": {
                    "start_date": str(plan.start_date),
                    "end_date": str(plan.end_date),
                    "workflows_started": current_started,
                    "workflows_completed": current_completed,
                    "workflows_failed": current_failed,
                    "ending_active_workflows": ending_active,
                    "average_completion_time_hours": (average_completion_hours),
                },
                "comparison_period": {
                    "start_date": str(
                        plan.comparison_start_date,
                    ),
                    "end_date": str(
                        plan.comparison_end_date,
                    ),
                    "workflows_completed": comparison_completed,
                },
                "completion_metric_completed_count": completed_count,
            },
            supporting_data=[
                AnalyticsEvidence(
                    key="workflows_started_during_period",
                    label="Workflows started during period",
                    value=current_started,
                    unit="workflows",
                    source="analytics_operations_daily",
                ),
                AnalyticsEvidence(
                    key="workflows_completed_during_period",
                    label="Workflows completed during period",
                    value=current_completed,
                    unit="workflows",
                    source="analytics_operations_daily",
                    comparison_value=comparison_completed,
                    comparison_change_percentage=self._percentage_change(
                        current_completed,
                        comparison_completed,
                    ),
                ),
                AnalyticsEvidence(
                    key="workflows_failed_during_period",
                    label="Workflows failed during period",
                    value=current_failed,
                    unit="workflows",
                    source="analytics_operations_daily",
                ),
                AnalyticsEvidence(
                    key="average_workflow_completion_time_hours",
                    label="Average workflow completion time",
                    value=average_completion_hours,
                    unit="hours",
                    source="workflow_executions",
                ),
                AnalyticsEvidence(
                    key="ending_active_workflows",
                    label="Active workflows at period end",
                    value=ending_active,
                    unit="workflows",
                    source="analytics_operations_daily",
                ),
            ],
        )
