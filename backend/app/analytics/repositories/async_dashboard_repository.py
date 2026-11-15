"""Native-async, tenant-scoped queries for the operations dashboard."""

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.compliance_case import ComplianceCase
from app.models.customer import Customer
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.task import Task
from app.models.user import User
from app.models.verification_case import IdentityVerificationCase
from app.models.workflow import WorkflowExecution
from app.utils.enums import (
    ComplianceCaseStatus,
    CustomerRiskLevel,
    CustomerStatus,
    TaskStatus,
    UserRole,
    VerificationStatus,
    WorkflowExecutionStatus,
)


class AsyncDashboardRepository:
    """Read dashboard aggregates for exactly one authenticated tenant."""

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active_tenant = db.info.get("tenant_id")
        if active_tenant is not None and active_tenant != tenant_id:
            raise ValueError(
                "Dashboard repository tenant does not match session tenant."
            )
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id

    @staticmethod
    def _date_range(
        start_date: date | None,
        end_date: date | None,
    ) -> tuple[datetime | None, datetime | None]:
        start_at = (
            datetime.combine(start_date, time.min, tzinfo=timezone.utc)
            if start_date is not None
            else None
        )
        end_at = (
            datetime.combine(
                end_date + timedelta(days=1), time.min, tzinfo=timezone.utc
            )
            if end_date is not None
            else None
        )
        return start_at, end_at

    @staticmethod
    def _add_date_filters(
        filters: list[Any],
        column: Any,
        start_at: datetime | None,
        end_at: datetime | None,
    ) -> None:
        if start_at is not None:
            filters.append(column >= start_at)
        if end_at is not None:
            filters.append(column < end_at)

    async def get_metrics(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        country: str | None = None,
        user_role: UserRole | None = None,
        now: datetime | None = None,
    ) -> dict[str, int]:
        start_at, end_at = self._date_range(start_date, end_date)
        current_time = now or datetime.now(timezone.utc)

        customer_filters: list[Any] = [Customer.tenant_id == self.tenant_id]
        self._add_date_filters(customer_filters, Customer.created_at, start_at, end_at)
        if country is not None:
            customer_filters.append(Customer.country_of_residence == country)

        # Keep the existing dashboard contract: total_customers and
        # new_registrations both reflect the selected customer/date filter.
        customer_count = int(
            await self.db.scalar(
                select(func.count(Customer.id)).where(*customer_filters)
            )
            or 0
        )
        pending_verification = int(
            await self.db.scalar(
                select(func.count(Customer.id)).where(
                    *customer_filters,
                    Customer.status == CustomerStatus.PENDING_VERIFICATION,
                )
            )
            or 0
        )
        verified_customers = int(
            await self.db.scalar(
                select(func.count(Customer.id)).where(
                    *customer_filters,
                    Customer.status == CustomerStatus.VERIFIED,
                )
            )
            or 0
        )

        workflow_filters: list[Any] = [WorkflowExecution.tenant_id == self.tenant_id]
        self._add_date_filters(
            workflow_filters, WorkflowExecution.started_at, start_at, end_at
        )
        workflow_query = select(func.count(WorkflowExecution.id)).select_from(
            WorkflowExecution
        )
        if country is not None:
            workflow_query = workflow_query.join(
                Customer,
                and_(
                    WorkflowExecution.entity_id == Customer.id,
                    func.lower(WorkflowExecution.entity_type) == "customer",
                ),
            )
            workflow_filters.extend(
                [
                    Customer.tenant_id == self.tenant_id,
                    Customer.country_of_residence == country,
                ]
            )
        if user_role is not None:
            workflow_query = workflow_query.join(
                User, WorkflowExecution.started_by == User.id
            )
            workflow_filters.extend(
                [User.tenant_id == self.tenant_id, User.role == user_role]
            )

        active_workflows = int(
            await self.db.scalar(
                workflow_query.where(
                    *workflow_filters,
                    WorkflowExecution.status == WorkflowExecutionStatus.IN_PROGRESS,
                )
            )
            or 0
        )
        completed_workflows = int(
            await self.db.scalar(
                workflow_query.where(
                    *workflow_filters,
                    WorkflowExecution.status == WorkflowExecutionStatus.COMPLETED,
                )
            )
            or 0
        )
        failed_workflows = int(
            await self.db.scalar(
                workflow_query.where(
                    *workflow_filters,
                    WorkflowExecution.status == WorkflowExecutionStatus.FAILED,
                )
            )
            or 0
        )

        task_filters: list[Any] = [Task.tenant_id == self.tenant_id]
        self._add_date_filters(task_filters, Task.created_at, start_at, end_at)
        task_query = select(func.count(Task.id)).select_from(Task)
        if country is not None:
            task_query = task_query.join(
                WorkflowExecution,
                Task.workflow_execution_id == WorkflowExecution.id,
            ).join(
                Customer,
                and_(
                    WorkflowExecution.entity_id == Customer.id,
                    func.lower(WorkflowExecution.entity_type) == "customer",
                ),
            )
            task_filters.extend(
                [
                    WorkflowExecution.tenant_id == self.tenant_id,
                    Customer.tenant_id == self.tenant_id,
                    Customer.country_of_residence == country,
                ]
            )
        if user_role is not None:
            task_query = task_query.join(User, Task.assigned_to == User.id)
            task_filters.extend(
                [User.tenant_id == self.tenant_id, User.role == user_role]
            )

        open_task_statuses = (
            TaskStatus.NEW,
            TaskStatus.ASSIGNED,
            TaskStatus.IN_PROGRESS,
        )
        open_tasks = int(
            await self.db.scalar(
                task_query.where(*task_filters, Task.status.in_(open_task_statuses))
            )
            or 0
        )
        completed_tasks = int(
            await self.db.scalar(
                task_query.where(*task_filters, Task.status == TaskStatus.COMPLETED)
            )
            or 0
        )
        overdue_tasks = int(
            await self.db.scalar(
                task_query.where(
                    *task_filters,
                    Task.status.in_(open_task_statuses),
                    Task.due_date.is_not(None),
                    Task.due_date < current_time,
                )
            )
            or 0
        )

        compliance_filters: list[Any] = [ComplianceCase.tenant_id == self.tenant_id]
        self._add_date_filters(
            compliance_filters, ComplianceCase.created_at, start_at, end_at
        )
        compliance_query = select(func.count(ComplianceCase.id)).select_from(
            ComplianceCase
        )
        if country is not None:
            compliance_query = compliance_query.join(
                Customer,
                ComplianceCase.customer_id == Customer.id,
            )
            compliance_filters.extend(
                [
                    Customer.tenant_id == self.tenant_id,
                    Customer.country_of_residence == country,
                ]
            )
        if user_role is not None:
            compliance_query = compliance_query.join(
                User, ComplianceCase.assigned_to == User.id
            )
            compliance_filters.extend(
                [User.tenant_id == self.tenant_id, User.role == user_role]
            )

        open_case_statuses = (
            ComplianceCaseStatus.OPEN,
            ComplianceCaseStatus.ASSIGNED,
            ComplianceCaseStatus.UNDER_REVIEW,
            ComplianceCaseStatus.ESCALATED,
        )
        open_cases = int(
            await self.db.scalar(
                compliance_query.where(
                    *compliance_filters,
                    ComplianceCase.status.in_(open_case_statuses),
                )
            )
            or 0
        )

        risk_filters: list[Any] = [
            Customer.tenant_id == self.tenant_id,
            CustomerRiskProfile.tenant_id == self.tenant_id,
            CustomerRiskProfile.risk_level.in_(
                (CustomerRiskLevel.HIGH, CustomerRiskLevel.CRITICAL)
            ),
        ]
        self._add_date_filters(risk_filters, Customer.created_at, start_at, end_at)
        risk_query = (
            select(func.count(Customer.id))
            .select_from(Customer)
            .join(CustomerRiskProfile, CustomerRiskProfile.customer_id == Customer.id)
        )
        if country is not None:
            risk_filters.append(Customer.country_of_residence == country)
        high_risk_customers = int(
            await self.db.scalar(risk_query.where(*risk_filters)) or 0
        )

        review_filters: list[Any] = [
            IdentityVerificationCase.tenant_id == self.tenant_id,
            IdentityVerificationCase.status == VerificationStatus.UNDER_REVIEW,
        ]
        self._add_date_filters(
            review_filters, IdentityVerificationCase.created_at, start_at, end_at
        )
        review_query = select(func.count(IdentityVerificationCase.id)).select_from(
            IdentityVerificationCase
        )
        if country is not None:
            review_query = review_query.join(
                Customer,
                IdentityVerificationCase.customer_id == Customer.id,
            )
            review_filters.extend(
                [
                    Customer.tenant_id == self.tenant_id,
                    Customer.country_of_residence == country,
                ]
            )
        if user_role is not None:
            review_query = review_query.join(
                User,
                IdentityVerificationCase.assigned_to == User.id,
            )
            review_filters.extend(
                [User.tenant_id == self.tenant_id, User.role == user_role]
            )
        pending_reviews = int(
            await self.db.scalar(review_query.where(*review_filters)) or 0
        )

        return {
            "total_customers": customer_count,
            "new_registrations": customer_count,
            "pending_verification": pending_verification,
            "verified_customers": verified_customers,
            "active_workflows": active_workflows,
            "completed_workflows": completed_workflows,
            "failed_workflows": failed_workflows,
            "open_tasks": open_tasks,
            "completed_tasks": completed_tasks,
            "overdue_tasks": overdue_tasks,
            "open_cases": open_cases,
            "high_risk_customers": high_risk_customers,
            "pending_reviews": pending_reviews,
        }
