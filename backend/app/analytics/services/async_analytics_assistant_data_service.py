"""Native-async data gathering for the AI analytics assistant."""

# ruff: noqa: E501
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.metrics.async_engine import AsyncMetricEngine
from app.analytics.metrics.async_measure_provider import AsyncMetricMeasureProvider
from app.analytics.models.customer_daily import CustomerAnalyticsDaily
from app.analytics.repositories.async_compliance_analytics_repository import (
    AsyncComplianceAnalyticsRepository,
)
from app.analytics.repositories.async_metric_repository import AsyncMetricRepository
from app.analytics.repositories.async_operations_analytics_repository import (
    AsyncOperationsAnalyticsRepository,
)
from app.schemas.ai_analytics_assistant import (
    AnalyticsEvidence,
    AnalyticsQuestionPlan,
    AnalyticsQuestionType,
)
from app.utils.enums import MetricStatus, MetricValueType
from app.utils.errors import bad_request


@dataclass(frozen=True)
class AsyncAnalyticsDataBundle:
    context: dict[str, Any]
    supporting_data: list[AnalyticsEvidence]


class AsyncAnalyticsAssistantDataService:
    """Build tenant-filtered analytics evidence without synchronous DB calls."""

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active_tenant_id = db.info.get("tenant_id")
        if active_tenant_id is not None and active_tenant_id != tenant_id:
            raise ValueError(
                "Analytics assistant tenant does not match the session tenant."
            )
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id
        self.compliance = AsyncComplianceAnalyticsRepository(db, tenant_id)
        self.operations = AsyncOperationsAnalyticsRepository(db, tenant_id)
        self.metrics = AsyncMetricRepository(db, tenant_id)
        self.metric_engine = AsyncMetricEngine(
            AsyncMetricMeasureProvider(db, tenant_id)
        )

    @staticmethod
    def _change(
        current: float | int | None,
        previous: float | int | None,
    ) -> float | None:
        if current is None or previous is None or float(previous) == 0:
            return None
        return round(
            (float(current) - float(previous)) / abs(float(previous)) * 100,
            2,
        )

    async def _customer_rows(
        self, start: Any, end: Any
    ) -> list[CustomerAnalyticsDaily]:
        result = await self.db.scalars(
            select(CustomerAnalyticsDaily)
            .where(
                CustomerAnalyticsDaily.tenant_id == self.tenant_id,
                CustomerAnalyticsDaily.snapshot_date >= start,
                CustomerAnalyticsDaily.snapshot_date <= end,
            )
            .order_by(CustomerAnalyticsDaily.snapshot_date)
        )
        return list(result.all())

    async def _customer_latest(self, end: Any) -> CustomerAnalyticsDaily | None:
        return await self.db.scalar(
            select(CustomerAnalyticsDaily)
            .where(
                CustomerAnalyticsDaily.tenant_id == self.tenant_id,
                CustomerAnalyticsDaily.snapshot_date <= end,
            )
            .order_by(CustomerAnalyticsDaily.snapshot_date.desc())
            .limit(1)
        )

    @staticmethod
    def _sum(rows: list[Any], field: str) -> int:
        return sum(int(getattr(row, field, 0) or 0) for row in rows)

    async def get_data(self, plan: AnalyticsQuestionPlan) -> AsyncAnalyticsDataBundle:
        handler = {
            AnalyticsQuestionType.CONFIGURED_METRIC: self._configured_metric,
            AnalyticsQuestionType.PENDING_VERIFICATION: self._pending_verification,
            AnalyticsQuestionType.VERIFICATION_REJECTION_REASONS: self._rejection_reasons,
            AnalyticsQuestionType.CUSTOMER_REGISTRATIONS: self._customer_registrations,
            AnalyticsQuestionType.RISK_DISTRIBUTION: self._risk_distribution,
            AnalyticsQuestionType.AML_ALERTS: self._aml_alerts,
            AnalyticsQuestionType.COMPLIANCE_CASES: self._compliance_cases,
            AnalyticsQuestionType.TASK_PERFORMANCE: self._task_performance,
            AnalyticsQuestionType.WORKFLOW_PERFORMANCE: self._workflow_performance,
        }.get(plan.question_type)
        if handler is None:
            raise bad_request("Unsupported analytics question type.")
        return await handler(plan)

    async def _configured_metric(
        self, plan: AnalyticsQuestionPlan
    ) -> AsyncAnalyticsDataBundle:
        if not plan.metric_key:
            raise bad_request("A metric key is required for this analytics question.")
        metric = await self.metrics.get_by_key(plan.metric_key)
        if metric is None or metric.status != MetricStatus.ACTIVE:
            raise bad_request(f"Analytics metric '{plan.metric_key}' is unavailable.")
        current = await self.metric_engine.calculate(
            metric=metric,
            start_date=plan.start_date,
            end_date=plan.end_date,
        )
        previous = await self.metric_engine.calculate(
            metric=metric,
            start_date=plan.comparison_start_date,
            end_date=plan.comparison_end_date,
        )
        change = self._change(current, previous)
        evidence = AnalyticsEvidence(
            key=metric.key,
            label=metric.name,
            value=current,
            unit="%" if metric.value_type == MetricValueType.PERCENTAGE else "seconds",
            source="metric_engine",
            comparison_value=previous,
            comparison_change_percentage=change,
            details={
                "description": metric.description,
                "period_start": str(plan.start_date),
                "period_end": str(plan.end_date),
                "comparison_start": str(plan.comparison_start_date),
                "comparison_end": str(plan.comparison_end_date),
            },
        )
        return AsyncAnalyticsDataBundle(
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
                    "value": current,
                },
                "comparison_period": {
                    "start_date": str(plan.comparison_start_date),
                    "end_date": str(plan.comparison_end_date),
                    "value": previous,
                },
                "change_percentage": change,
            },
            supporting_data=[evidence],
        )

    async def _pending_verification(
        self, plan: AnalyticsQuestionPlan
    ) -> AsyncAnalyticsDataBundle:
        current = await self._customer_latest(plan.end_date)
        previous = await self._customer_latest(plan.comparison_end_date)
        value = current.ending_pending_verification_customers if current else None
        old = previous.ending_pending_verification_customers if previous else None
        change = self._change(value, old)
        evidence = AnalyticsEvidence(
            key="pending_verification_customers",
            label="Pending verification customers at period end",
            value=value,
            unit="customers",
            source="analytics_customer_daily",
            comparison_value=old,
            comparison_change_percentage=change,
            details={
                "current_snapshot_date": (
                    str(current.snapshot_date) if current else None
                ),
                "comparison_snapshot_date": (
                    str(previous.snapshot_date) if previous else None
                ),
            },
        )
        return AsyncAnalyticsDataBundle(
            context={
                "question_type": plan.question_type.value,
                "period": {
                    "start_date": str(plan.start_date),
                    "end_date": str(plan.end_date),
                    "pending_verification_customers": value,
                },
                "comparison_period": {
                    "start_date": str(plan.comparison_start_date),
                    "end_date": str(plan.comparison_end_date),
                    "pending_verification_customers": old,
                },
                "change_percentage": change,
            },
            supporting_data=[evidence],
        )

    async def _rejection_reasons(
        self, plan: AnalyticsQuestionPlan
    ) -> AsyncAnalyticsDataBundle:
        rows = await self.compliance.get_verification_rejection_reasons(
            start_date=plan.start_date,
            end_date=plan.end_date,
        )
        old_rows = await self.compliance.get_verification_rejection_reasons(
            start_date=plan.comparison_start_date,
            end_date=plan.comparison_end_date,
        )
        total = sum(count for _, count in rows)
        if rows:
            name, count = rows[0]
            share = round(count / total * 100, 2) if total else None
            old_count = dict(old_rows).get(name)
            change = self._change(count, old_count)
        else:
            name, count, share, old_count, change = None, 0, None, None, None
        evidence = AnalyticsEvidence(
            key="top_verification_rejection_reason",
            label="Top verification rejection reason",
            value=name,
            source="verification_reviews",
            comparison_value=old_count if name else None,
            comparison_change_percentage=change,
            details={
                "count": count,
                "share_percentage": share,
                "top_reasons": [
                    {"reason": reason, "count": value} for reason, value in rows[:5]
                ],
                "total_rejections": total,
            },
        )
        return AsyncAnalyticsDataBundle(
            context={
                "question_type": plan.question_type.value,
                "period": {
                    "start_date": str(plan.start_date),
                    "end_date": str(plan.end_date),
                    "total_rejections": total,
                    "top_reason": name,
                    "top_reason_count": count,
                    "top_reasons": [
                        {"reason": reason, "count": value}
                        for reason, value in rows[:10]
                    ],
                },
                "comparison_period": {
                    "start_date": str(plan.comparison_start_date),
                    "end_date": str(plan.comparison_end_date),
                    "top_reasons": [
                        {"reason": reason, "count": value}
                        for reason, value in old_rows[:10]
                    ],
                },
            },
            supporting_data=[evidence],
        )

    async def _customer_registrations(
        self, plan: AnalyticsQuestionPlan
    ) -> AsyncAnalyticsDataBundle:
        rows = await self._customer_rows(plan.start_date, plan.end_date)
        old_rows = await self._customer_rows(
            plan.comparison_start_date, plan.comparison_end_date
        )
        value = self._sum(rows, "customers_registered_during_day")
        old = self._sum(old_rows, "customers_registered_during_day")
        change = self._change(value, old)
        evidence = AnalyticsEvidence(
            key="customers_registered_during_period",
            label="Customers registered during period",
            value=value,
            unit="customers",
            source="analytics_customer_daily",
            comparison_value=old,
            comparison_change_percentage=change,
        )
        return AsyncAnalyticsDataBundle(
            context={
                "question_type": plan.question_type.value,
                "period": {
                    "start_date": str(plan.start_date),
                    "end_date": str(plan.end_date),
                    "customers_registered": value,
                },
                "comparison_period": {
                    "start_date": str(plan.comparison_start_date),
                    "end_date": str(plan.comparison_end_date),
                    "customers_registered": old,
                },
                "change_percentage": change,
            },
            supporting_data=[evidence],
        )

    async def _risk_distribution(
        self, plan: AnalyticsQuestionPlan
    ) -> AsyncAnalyticsDataBundle:
        current = await self.compliance.get_latest_snapshot(end_date=plan.end_date)
        previous = await self.compliance.get_latest_snapshot(
            end_date=plan.comparison_end_date
        )
        fields = {
            "LOW": "ending_low_risk_customers",
            "MEDIUM": "ending_medium_risk_customers",
            "HIGH": "ending_high_risk_customers",
            "CRITICAL": "ending_critical_risk_customers",
        }
        values = {
            level: int(getattr(current, field) if current else 0)
            for level, field in fields.items()
        }
        old = {
            level: int(getattr(previous, field) if previous else 0)
            for level, field in fields.items()
        }
        evidence = [
            AnalyticsEvidence(
                key=f"risk_{level.lower()}_customers",
                label=f"{level.title()} risk customers",
                value=value,
                unit="customers",
                source="analytics_compliance_daily",
                comparison_value=old[level],
                comparison_change_percentage=self._change(value, old[level]),
            )
            for level, value in values.items()
        ]
        return AsyncAnalyticsDataBundle(
            context={
                "question_type": plan.question_type.value,
                "period": {
                    "start_date": str(plan.start_date),
                    "end_date": str(plan.end_date),
                    "risk_distribution": values,
                },
                "comparison_period": {
                    "start_date": str(plan.comparison_start_date),
                    "end_date": str(plan.comparison_end_date),
                    "risk_distribution": old,
                },
            },
            supporting_data=evidence,
        )

    async def _aml_alerts(
        self, plan: AnalyticsQuestionPlan
    ) -> AsyncAnalyticsDataBundle:
        rows = await self.compliance.get_daily_snapshots(
            start_date=plan.start_date, end_date=plan.end_date
        )
        old_rows = await self.compliance.get_daily_snapshots(
            start_date=plan.comparison_start_date,
            end_date=plan.comparison_end_date,
        )
        created = self._sum(rows, "alerts_created_during_day")
        old_created = self._sum(old_rows, "alerts_created_during_day")
        current = await self.compliance.get_latest_snapshot(end_date=plan.end_date)
        previous = await self.compliance.get_latest_snapshot(
            end_date=plan.comparison_end_date
        )
        total = int(current.ending_total_alerts) if current else 0
        old_total = int(previous.ending_total_alerts) if previous else 0
        evidence = [
            AnalyticsEvidence(
                key="alerts_created_during_period",
                label="AML alerts created during period",
                value=created,
                unit="alerts",
                source="analytics_compliance_daily",
                comparison_value=old_created,
                comparison_change_percentage=self._change(created, old_created),
            ),
            AnalyticsEvidence(
                key="ending_total_alerts",
                label="Total AML alerts at period end",
                value=total,
                unit="alerts",
                source="analytics_compliance_daily",
                comparison_value=old_total,
                comparison_change_percentage=self._change(total, old_total),
            ),
        ]
        return AsyncAnalyticsDataBundle(
            context={
                "question_type": plan.question_type.value,
                "period": {
                    "start_date": str(plan.start_date),
                    "end_date": str(plan.end_date),
                    "alerts_created": created,
                    "ending_total_alerts": total,
                },
                "comparison_period": {
                    "start_date": str(plan.comparison_start_date),
                    "end_date": str(plan.comparison_end_date),
                    "alerts_created": old_created,
                    "ending_total_alerts": old_total,
                },
            },
            supporting_data=evidence,
        )

    async def _compliance_cases(
        self, plan: AnalyticsQuestionPlan
    ) -> AsyncAnalyticsDataBundle:
        rows = await self.compliance.get_daily_snapshots(
            start_date=plan.start_date, end_date=plan.end_date
        )
        old_rows = await self.compliance.get_daily_snapshots(
            start_date=plan.comparison_start_date,
            end_date=plan.comparison_end_date,
        )
        created = self._sum(rows, "cases_created_during_day")
        old_created = self._sum(old_rows, "cases_created_during_day")
        current = await self.compliance.get_latest_snapshot(end_date=plan.end_date)
        previous = await self.compliance.get_latest_snapshot(
            end_date=plan.comparison_end_date
        )
        opened = int(current.ending_open_cases) if current else 0
        old_opened = int(previous.ending_open_cases) if previous else 0
        closed = int(current.ending_closed_cases) if current else 0
        old_closed = int(previous.ending_closed_cases) if previous else 0
        evidence = [
            AnalyticsEvidence(
                key="cases_created_during_period",
                label="Compliance cases created during period",
                value=created,
                unit="cases",
                source="analytics_compliance_daily",
                comparison_value=old_created,
                comparison_change_percentage=self._change(created, old_created),
            ),
            AnalyticsEvidence(
                key="ending_open_cases",
                label="Open compliance cases at period end",
                value=opened,
                unit="cases",
                source="analytics_compliance_daily",
                comparison_value=old_opened,
                comparison_change_percentage=self._change(opened, old_opened),
            ),
            AnalyticsEvidence(
                key="ending_closed_cases",
                label="Closed compliance cases at period end",
                value=closed,
                unit="cases",
                source="analytics_compliance_daily",
                comparison_value=old_closed,
                comparison_change_percentage=self._change(closed, old_closed),
            ),
        ]
        return AsyncAnalyticsDataBundle(
            context={
                "question_type": plan.question_type.value,
                "period": {
                    "start_date": str(plan.start_date),
                    "end_date": str(plan.end_date),
                    "cases_created": created,
                    "ending_open_cases": opened,
                    "ending_closed_cases": closed,
                },
                "comparison_period": {
                    "start_date": str(plan.comparison_start_date),
                    "end_date": str(plan.comparison_end_date),
                    "cases_created": old_created,
                    "ending_open_cases": old_opened,
                    "ending_closed_cases": old_closed,
                },
            },
            supporting_data=evidence,
        )

    async def _task_performance(
        self, plan: AnalyticsQuestionPlan
    ) -> AsyncAnalyticsDataBundle:
        rows = await self.operations.get_daily_snapshots(
            start_date=plan.start_date, end_date=plan.end_date
        )
        old_rows = await self.operations.get_daily_snapshots(
            start_date=plan.comparison_start_date,
            end_date=plan.comparison_end_date,
        )
        completed = self._sum(rows, "tasks_completed_during_day")
        old_completed = self._sum(old_rows, "tasks_completed_during_day")
        within = self._sum(rows, "tasks_completed_within_sla_during_day")
        breached = self._sum(rows, "tasks_completed_breached_sla_during_day")
        snapshot = await self.operations.get_latest_snapshot(end_date=plan.end_date)
        opened = int(snapshot.ending_open_tasks) if snapshot else 0
        overdue = int(snapshot.ending_overdue_tasks) if snapshot else 0
        sla = round(within / completed * 100, 2) if completed else None
        count, average = await self.operations.get_task_resolution_metrics(
            start_date=plan.start_date, end_date=plan.end_date
        )
        evidence = [
            AnalyticsEvidence(
                key="tasks_completed_during_period",
                label="Tasks completed during period",
                value=completed,
                unit="tasks",
                source="analytics_operations_daily",
                comparison_value=old_completed,
                comparison_change_percentage=self._change(completed, old_completed),
            ),
            AnalyticsEvidence(
                key="ending_overdue_tasks",
                label="Overdue tasks at period end",
                value=overdue,
                unit="tasks",
                source="analytics_operations_daily",
            ),
            AnalyticsEvidence(
                key="task_sla_compliance_percentage",
                label="Task SLA compliance",
                value=sla,
                unit="%",
                source="analytics_operations_daily",
            ),
            AnalyticsEvidence(
                key="average_task_resolution_time_hours",
                label="Average task resolution time",
                value=average,
                unit="hours",
                source="tasks",
            ),
        ]
        return AsyncAnalyticsDataBundle(
            context={
                "question_type": plan.question_type.value,
                "period": {
                    "start_date": str(plan.start_date),
                    "end_date": str(plan.end_date),
                    "tasks_completed": completed,
                    "ending_open_tasks": opened,
                    "ending_overdue_tasks": overdue,
                    "tasks_completed_within_sla": within,
                    "tasks_completed_breached_sla": breached,
                    "sla_compliance_percentage": sla,
                    "average_resolution_time_hours": average,
                },
                "comparison_period": {
                    "start_date": str(plan.comparison_start_date),
                    "end_date": str(plan.comparison_end_date),
                    "tasks_completed": old_completed,
                },
                "resolution_metric_completed_count": count,
            },
            supporting_data=evidence,
        )

    async def _workflow_performance(
        self, plan: AnalyticsQuestionPlan
    ) -> AsyncAnalyticsDataBundle:
        rows = await self.operations.get_daily_snapshots(
            start_date=plan.start_date, end_date=plan.end_date
        )
        old_rows = await self.operations.get_daily_snapshots(
            start_date=plan.comparison_start_date,
            end_date=plan.comparison_end_date,
        )
        started = self._sum(rows, "workflows_started_during_day")
        completed = self._sum(rows, "workflows_completed_during_day")
        failed = self._sum(rows, "workflows_failed_during_day")
        old_completed = self._sum(old_rows, "workflows_completed_during_day")
        snapshot = await self.operations.get_latest_snapshot(end_date=plan.end_date)
        active = int(snapshot.ending_active_workflows) if snapshot else 0
        count, average = await self.operations.get_workflow_completion_metrics(
            start_date=plan.start_date, end_date=plan.end_date
        )
        evidence = [
            AnalyticsEvidence(
                key="workflows_started_during_period",
                label="Workflows started during period",
                value=started,
                unit="workflows",
                source="analytics_operations_daily",
            ),
            AnalyticsEvidence(
                key="workflows_completed_during_period",
                label="Workflows completed during period",
                value=completed,
                unit="workflows",
                source="analytics_operations_daily",
                comparison_value=old_completed,
                comparison_change_percentage=self._change(completed, old_completed),
            ),
            AnalyticsEvidence(
                key="workflows_failed_during_period",
                label="Workflows failed during period",
                value=failed,
                unit="workflows",
                source="analytics_operations_daily",
            ),
            AnalyticsEvidence(
                key="average_workflow_completion_time_hours",
                label="Average workflow completion time",
                value=average,
                unit="hours",
                source="workflow_executions",
            ),
            AnalyticsEvidence(
                key="ending_active_workflows",
                label="Active workflows at period end",
                value=active,
                unit="workflows",
                source="analytics_operations_daily",
            ),
        ]
        return AsyncAnalyticsDataBundle(
            context={
                "question_type": plan.question_type.value,
                "period": {
                    "start_date": str(plan.start_date),
                    "end_date": str(plan.end_date),
                    "workflows_started": started,
                    "workflows_completed": completed,
                    "workflows_failed": failed,
                    "ending_active_workflows": active,
                    "average_completion_time_hours": average,
                },
                "comparison_period": {
                    "start_date": str(plan.comparison_start_date),
                    "end_date": str(plan.comparison_end_date),
                    "workflows_completed": old_completed,
                },
                "completion_metric_completed_count": count,
            },
            supporting_data=evidence,
        )
