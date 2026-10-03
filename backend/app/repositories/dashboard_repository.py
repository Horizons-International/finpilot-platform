from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

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


class DashboardRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _date_range(
        start_date: date | None,
        end_date: date | None,
    ) -> tuple[datetime | None, datetime | None]:
        start_at = (
            datetime.combine(
                start_date,
                time.min,
                tzinfo=timezone.utc,
            )
            if start_date is not None
            else None
        )

        end_at = (
            datetime.combine(
                end_date + timedelta(days=1),
                time.min,
                tzinfo=timezone.utc,
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

    def get_metrics(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        country: str | None = None,
        user_role: UserRole | None = None,
        now: datetime | None = None,
    ) -> dict[str, int]:
        start_at, end_at = self._date_range(
            start_date,
            end_date,
        )

        current_time = now or datetime.now(timezone.utc)

        # ------------------------------------------------------------------
        # Customer metrics
        # ------------------------------------------------------------------

        customer_filters: list[Any] = []

        self._add_date_filters(
            customer_filters,
            Customer.created_at,
            start_at,
            end_at,
        )

        if country is not None:
            customer_filters.append(
                Customer.country_of_residence == country,
            )

        total_customers = self.db.execute(
            select(func.count(Customer.id)).where(
                *customer_filters,
            )
        ).scalar_one()

        new_registrations = self.db.execute(
            select(func.count(Customer.id)).where(
                *customer_filters,
            )
        ).scalar_one()

        pending_verification_filters = [
            *customer_filters,
            Customer.status == CustomerStatus.PENDING_VERIFICATION,
        ]

        pending_verification = self.db.execute(
            select(func.count(Customer.id)).where(
                *pending_verification_filters,
            )
        ).scalar_one()

        verified_filters = [
            *customer_filters,
            Customer.status == CustomerStatus.VERIFIED,
        ]

        verified_customers = self.db.execute(
            select(func.count(Customer.id)).where(
                *verified_filters,
            )
        ).scalar_one()

        # ------------------------------------------------------------------
        # Workflow metrics
        # ------------------------------------------------------------------

        workflow_filters: list[Any] = []

        self._add_date_filters(
            workflow_filters,
            WorkflowExecution.started_at,
            start_at,
            end_at,
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

            workflow_filters.append(
                Customer.country_of_residence == country,
            )

        if user_role is not None:
            workflow_query = workflow_query.join(
                User,
                WorkflowExecution.started_by == User.id,
            )

            workflow_filters.append(
                User.role == user_role,
            )

        active_workflows = self.db.execute(
            workflow_query.where(
                *workflow_filters,
                WorkflowExecution.status == WorkflowExecutionStatus.IN_PROGRESS,
            )
        ).scalar_one()

        completed_workflows = self.db.execute(
            workflow_query.where(
                *workflow_filters,
                WorkflowExecution.status == WorkflowExecutionStatus.COMPLETED,
            )
        ).scalar_one()

        failed_workflows = self.db.execute(
            workflow_query.where(
                *workflow_filters,
                WorkflowExecution.status == WorkflowExecutionStatus.FAILED,
            )
        ).scalar_one()

        # ------------------------------------------------------------------
        # Task metrics
        # ------------------------------------------------------------------

        task_filters: list[Any] = []

        self._add_date_filters(
            task_filters,
            Task.created_at,
            start_at,
            end_at,
        )

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

            task_filters.append(
                Customer.country_of_residence == country,
            )

        if user_role is not None:
            task_query = task_query.join(
                User,
                Task.assigned_to == User.id,
            )

            task_filters.append(
                User.role == user_role,
            )

        open_task_statuses = (
            TaskStatus.NEW,
            TaskStatus.ASSIGNED,
            TaskStatus.IN_PROGRESS,
        )

        open_tasks = self.db.execute(
            task_query.where(
                *task_filters,
                Task.status.in_(open_task_statuses),
            )
        ).scalar_one()

        completed_tasks = self.db.execute(
            task_query.where(
                *task_filters,
                Task.status == TaskStatus.COMPLETED,
            )
        ).scalar_one()

        overdue_tasks = self.db.execute(
            task_query.where(
                *task_filters,
                Task.status.in_(open_task_statuses),
                Task.due_date.is_not(None),
                Task.due_date < current_time,
            )
        ).scalar_one()

        # ------------------------------------------------------------------
        # Compliance metrics
        # ------------------------------------------------------------------

        compliance_filters: list[Any] = []

        self._add_date_filters(
            compliance_filters,
            ComplianceCase.created_at,
            start_at,
            end_at,
        )

        compliance_query = select(func.count(ComplianceCase.id)).select_from(
            ComplianceCase
        )

        if country is not None:
            compliance_query = compliance_query.join(
                Customer,
                ComplianceCase.customer_id == Customer.id,
            )

            compliance_filters.append(
                Customer.country_of_residence == country,
            )

        if user_role is not None:
            compliance_query = compliance_query.join(
                User,
                ComplianceCase.assigned_to == User.id,
            )

            compliance_filters.append(
                User.role == user_role,
            )

        open_case_statuses = (
            ComplianceCaseStatus.OPEN,
            ComplianceCaseStatus.ASSIGNED,
            ComplianceCaseStatus.UNDER_REVIEW,
            ComplianceCaseStatus.ESCALATED,
        )

        open_cases = self.db.execute(
            compliance_query.where(
                *compliance_filters,
                ComplianceCase.status.in_(open_case_statuses),
            )
        ).scalar_one()

        # ------------------------------------------------------------------
        # High-risk customers
        # ------------------------------------------------------------------

        risk_filters: list[Any] = [
            CustomerRiskProfile.risk_level.in_(
                (
                    CustomerRiskLevel.HIGH,
                    CustomerRiskLevel.CRITICAL,
                )
            )
        ]

        self._add_date_filters(
            risk_filters,
            Customer.created_at,
            start_at,
            end_at,
        )

        risk_query = (
            select(func.count(Customer.id))
            .select_from(Customer)
            .join(
                CustomerRiskProfile,
                CustomerRiskProfile.customer_id == Customer.id,
            )
        )

        if country is not None:
            risk_filters.append(
                Customer.country_of_residence == country,
            )

        high_risk_customers = self.db.execute(
            risk_query.where(
                *risk_filters,
            )
        ).scalar_one()

        # ------------------------------------------------------------------
        # Pending verification reviews
        # ------------------------------------------------------------------

        review_filters: list[Any] = [
            IdentityVerificationCase.status == VerificationStatus.UNDER_REVIEW,
        ]

        self._add_date_filters(
            review_filters,
            IdentityVerificationCase.created_at,
            start_at,
            end_at,
        )

        review_query = select(func.count(IdentityVerificationCase.id)).select_from(
            IdentityVerificationCase
        )

        if country is not None:
            review_query = review_query.join(
                Customer,
                IdentityVerificationCase.customer_id == Customer.id,
            )

            review_filters.append(
                Customer.country_of_residence == country,
            )

        if user_role is not None:
            review_query = review_query.join(
                User,
                IdentityVerificationCase.assigned_to == User.id,
            )

            review_filters.append(
                User.role == user_role,
            )

        pending_reviews = self.db.execute(
            review_query.where(
                *review_filters,
            )
        ).scalar_one()

        return {
            "total_customers": int(total_customers),
            "new_registrations": int(new_registrations),
            "pending_verification": int(pending_verification),
            "verified_customers": int(verified_customers),
            "active_workflows": int(active_workflows),
            "completed_workflows": int(completed_workflows),
            "failed_workflows": int(failed_workflows),
            "open_tasks": int(open_tasks),
            "completed_tasks": int(completed_tasks),
            "overdue_tasks": int(overdue_tasks),
            "open_cases": int(open_cases),
            "high_risk_customers": int(high_risk_customers),
            "pending_reviews": int(pending_reviews),
        }
