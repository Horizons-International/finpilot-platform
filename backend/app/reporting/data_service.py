from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.models.compliance_case import ComplianceCase
from app.models.customer import Customer
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.task import Task
from app.models.verification_case import IdentityVerificationCase
from app.models.workflow import Workflow, WorkflowExecution
from app.schemas.report_exports import ReportFilters
from app.utils.enums import ReportType


@dataclass(frozen=True)
class ReportTable:
    title: str
    columns: list[str]
    rows: list[list[Any]]


class ReportingDataService:
    def __init__(
        self,
        db: Session,
        tenant_id: UUID,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id

    @staticmethod
    def _date_bounds(
        filters: ReportFilters,
    ) -> tuple[datetime | None, datetime | None]:
        start = (
            datetime.combine(
                filters.start_date,
                time.min,
                tzinfo=timezone.utc,
            )
            if filters.start_date is not None
            else None
        )

        end = (
            datetime.combine(
                filters.end_date + timedelta(days=1),
                time.min,
                tzinfo=timezone.utc,
            )
            if filters.end_date is not None
            else None
        )

        return start, end

    def count_rows(
        self,
        *,
        report_type: ReportType,
        filters: ReportFilters,
    ) -> int:
        if report_type == ReportType.CUSTOMER:
            return self._count_customer_rows(filters)

        if report_type == ReportType.VERIFICATION:
            return self._count_verification_rows(filters)

        if report_type == ReportType.COMPLIANCE:
            return self._count_compliance_rows(filters)

        if report_type == ReportType.OPERATIONAL_PERFORMANCE:
            return self._count_task_rows(filters) + self._count_workflow_rows(filters)

        raise ValueError(
            f"Unsupported report type: {report_type}",
        )

    def build_report(
        self,
        *,
        report_type: ReportType,
        filters: ReportFilters,
    ) -> ReportTable:
        if report_type == ReportType.CUSTOMER:
            return self._build_customer_report(filters)

        if report_type == ReportType.VERIFICATION:
            return self._build_verification_report(filters)

        if report_type == ReportType.COMPLIANCE:
            return self._build_compliance_report(filters)

        if report_type == ReportType.OPERATIONAL_PERFORMANCE:
            return self._build_operational_report(filters)

        raise ValueError(
            f"Unsupported report type: {report_type}",
        )

    def _customer_statement(
        self,
        filters: ReportFilters,
        *,
        count_only: bool = False,
    ) -> Select[Any]:
        start, end = self._date_bounds(filters)

        statement: Any

        if count_only:
            statement = select(func.count(Customer.id)).select_from(Customer)
        else:
            statement = (
                select(
                    Customer,
                    CustomerRiskProfile,
                )
                .select_from(Customer)
                .outerjoin(
                    CustomerRiskProfile,
                    CustomerRiskProfile.customer_id == Customer.id,
                )
            )

        if start is not None:
            statement = statement.where(
                Customer.created_at >= start,
            )

        if end is not None:
            statement = statement.where(
                Customer.created_at < end,
            )

        if filters.country is not None:
            statement = statement.where(
                func.upper(Customer.country_of_residence) == filters.country.upper(),
            )

        if filters.customer_status is not None:
            statement = statement.where(
                Customer.status == filters.customer_status,
            )

        if filters.risk_level is not None:
            statement = statement.where(
                CustomerRiskProfile.risk_level == filters.risk_level,
            )

        statement = statement.where(
            Customer.tenant_id == self.tenant_id,
        )

        return cast(Select[Any], statement)

    def _count_customer_rows(
        self,
        filters: ReportFilters,
    ) -> int:
        return int(
            self.db.scalar(
                self._customer_statement(
                    filters,
                    count_only=True,
                ),
            )
            or 0
        )

    def _build_customer_report(
        self,
        filters: ReportFilters,
    ) -> ReportTable:
        statement = self._customer_statement(filters)

        records = self.db.execute(
            statement.order_by(
                Customer.created_at.desc(),
            ),
        ).all()

        rows = [
            [
                customer.id,
                (
                    f"{customer.first_name} "
                    f"{customer.middle_name or ''} "
                    f"{customer.last_name}"
                ).strip(),
                customer.email,
                customer.phone_number,
                customer.nationality,
                customer.country_of_residence,
                customer.status.value,
                risk_profile.risk_level.value if risk_profile is not None else None,
                risk_profile.risk_score if risk_profile is not None else None,
                customer.created_at,
            ]
            for customer, risk_profile in records
        ]

        return ReportTable(
            title="Customer Report",
            columns=[
                "Customer ID",
                "Customer Name",
                "Email",
                "Phone Number",
                "Nationality",
                "Country of Residence",
                "Customer Status",
                "Risk Level",
                "Risk Score",
                "Created At",
            ],
            rows=rows,
        )

    def _verification_statement(
        self,
        filters: ReportFilters,
        *,
        count_only: bool = False,
    ) -> Select[Any]:
        start, end = self._date_bounds(filters)

        statement: Any

        if count_only:
            statement = (
                select(func.count(IdentityVerificationCase.id))
                .select_from(IdentityVerificationCase)
                .join(
                    Customer,
                    Customer.id == IdentityVerificationCase.customer_id,
                )
                .outerjoin(
                    CustomerRiskProfile,
                    CustomerRiskProfile.customer_id == Customer.id,
                )
            )
        else:
            statement = (
                select(
                    IdentityVerificationCase,
                    Customer,
                    CustomerRiskProfile,
                )
                .select_from(IdentityVerificationCase)
                .join(
                    Customer,
                    Customer.id == IdentityVerificationCase.customer_id,
                )
                .outerjoin(
                    CustomerRiskProfile,
                    CustomerRiskProfile.customer_id == Customer.id,
                )
            )

        if start is not None:
            statement = statement.where(
                IdentityVerificationCase.created_at >= start,
            )

        if end is not None:
            statement = statement.where(
                IdentityVerificationCase.created_at < end,
            )

        if filters.country is not None:
            statement = statement.where(
                func.upper(Customer.country_of_residence) == filters.country.upper(),
            )

        if filters.risk_level is not None:
            statement = statement.where(
                CustomerRiskProfile.risk_level == filters.risk_level,
            )

        if filters.verification_status is not None:
            statement = statement.where(
                IdentityVerificationCase.status == filters.verification_status,
            )

        if filters.verification_type is not None:
            statement = statement.where(
                IdentityVerificationCase.verification_type == filters.verification_type,
            )

        statement = statement.where(
            Customer.tenant_id == self.tenant_id,
        )

        return cast(Select[Any], statement)

    def _count_verification_rows(
        self,
        filters: ReportFilters,
    ) -> int:
        return int(
            self.db.scalar(
                self._verification_statement(
                    filters,
                    count_only=True,
                ),
            )
            or 0
        )

    def _build_verification_report(
        self,
        filters: ReportFilters,
    ) -> ReportTable:
        statement = self._verification_statement(filters)

        records = self.db.execute(
            statement.order_by(
                IdentityVerificationCase.created_at.desc(),
            ),
        ).all()

        rows = [
            [
                verification_case.id,
                verification_case.customer_id,
                (f"{customer.first_name} {customer.last_name}"),
                customer.country_of_residence,
                (risk_profile.risk_level.value if risk_profile is not None else None),
                verification_case.verification_type.value,
                verification_case.status.value,
                verification_case.assigned_to,
                verification_case.created_at,
                verification_case.completed_at,
            ]
            for verification_case, customer, risk_profile in records
        ]

        return ReportTable(
            title="Verification Report",
            columns=[
                "Verification Case ID",
                "Customer ID",
                "Customer Name",
                "Country",
                "Risk Level",
                "Verification Type",
                "Verification Status",
                "Assigned Reviewer ID",
                "Created At",
                "Completed At",
            ],
            rows=rows,
        )

    def _compliance_statement(
        self,
        filters: ReportFilters,
        *,
        count_only: bool = False,
    ) -> Select[Any]:
        start, end = self._date_bounds(filters)

        statement: Any

        if count_only:
            statement = (
                select(func.count(ComplianceCase.id))
                .select_from(ComplianceCase)
                .join(
                    Customer,
                    Customer.id == ComplianceCase.customer_id,
                )
                .outerjoin(
                    CustomerRiskProfile,
                    CustomerRiskProfile.customer_id == Customer.id,
                )
            )
        else:
            statement = (
                select(
                    ComplianceCase,
                    Customer,
                    CustomerRiskProfile,
                )
                .select_from(ComplianceCase)
                .join(
                    Customer,
                    Customer.id == ComplianceCase.customer_id,
                )
                .outerjoin(
                    CustomerRiskProfile,
                    CustomerRiskProfile.customer_id == Customer.id,
                )
            )

        if start is not None:
            statement = statement.where(
                ComplianceCase.created_at >= start,
            )

        if end is not None:
            statement = statement.where(
                ComplianceCase.created_at < end,
            )

        if filters.country is not None:
            statement = statement.where(
                func.upper(Customer.country_of_residence) == filters.country.upper(),
            )

        if filters.risk_level is not None:
            statement = statement.where(
                CustomerRiskProfile.risk_level == filters.risk_level,
            )

        if filters.compliance_status is not None:
            statement = statement.where(
                ComplianceCase.status == filters.compliance_status,
            )

        statement = statement.where(
            Customer.tenant_id == self.tenant_id,
        )

        return cast(Select[Any], statement)

    def _count_compliance_rows(
        self,
        filters: ReportFilters,
    ) -> int:
        return int(
            self.db.scalar(
                self._compliance_statement(
                    filters,
                    count_only=True,
                ),
            )
            or 0
        )

    def _build_compliance_report(
        self,
        filters: ReportFilters,
    ) -> ReportTable:
        statement = self._compliance_statement(filters)

        records = self.db.execute(
            statement.order_by(
                ComplianceCase.created_at.desc(),
            ),
        ).all()

        rows = [
            [
                compliance_case.id,
                compliance_case.customer_id,
                (f"{customer.first_name} {customer.last_name}"),
                customer.country_of_residence,
                (risk_profile.risk_level.value if risk_profile is not None else None),
                compliance_case.case_type.value,
                compliance_case.priority.value,
                compliance_case.status.value,
                compliance_case.assigned_to,
                compliance_case.resolution_reason,
                compliance_case.created_at,
                compliance_case.closed_at,
            ]
            for compliance_case, customer, risk_profile in records
        ]

        return ReportTable(
            title="Compliance Report",
            columns=[
                "Compliance Case ID",
                "Customer ID",
                "Customer Name",
                "Country",
                "Risk Level",
                "Case Type",
                "Priority",
                "Status",
                "Assigned User ID",
                "Resolution Reason",
                "Created At",
                "Closed At",
            ],
            rows=rows,
        )

    def _task_statement(
        self,
        filters: ReportFilters,
        *,
        count_only: bool = False,
    ):
        start, end = self._date_bounds(filters)

        statement = select(func.count(Task.id)) if count_only else select(Task)

        if start is not None:
            statement = statement.where(
                Task.created_at >= start,
            )

        if end is not None:
            statement = statement.where(
                Task.created_at < end,
            )

        if filters.task_status is not None:
            statement = statement.where(
                Task.status == filters.task_status,
            )

        return statement

    def _count_task_rows(
        self,
        filters: ReportFilters,
    ) -> int:
        return int(
            self.db.scalar(
                self._task_statement(
                    filters,
                    count_only=True,
                ),
            )
            or 0
        )

    def _workflow_statement(
        self,
        filters: ReportFilters,
        *,
        count_only: bool = False,
    ) -> Select[Any]:
        start, end = self._date_bounds(filters)

        if count_only:
            statement = cast(
                Select[Any],
                select(func.count(WorkflowExecution.id))
                .select_from(WorkflowExecution)
                .join(
                    Workflow,
                    Workflow.id == WorkflowExecution.workflow_id,
                ),
            )
        else:
            statement = cast(
                Select[Any],
                select(
                    WorkflowExecution,
                    Workflow,
                ).join(
                    Workflow,
                    Workflow.id == WorkflowExecution.workflow_id,
                ),
            )

        if start is not None:
            statement = statement.where(
                WorkflowExecution.started_at >= start,
            )

        if end is not None:
            statement = statement.where(
                WorkflowExecution.started_at < end,
            )

        if filters.workflow_status is not None:
            statement = statement.where(
                WorkflowExecution.status == filters.workflow_status,
            )

        statement = statement.where(
            Workflow.tenant_id == self.tenant_id,
        )

        return statement

    def _count_workflow_rows(
        self,
        filters: ReportFilters,
    ) -> int:
        return int(
            self.db.scalar(
                self._workflow_statement(
                    filters,
                    count_only=True,
                ),
            )
            or 0
        )

    def _build_operational_report(
        self,
        filters: ReportFilters,
    ) -> ReportTable:
        task_statement = self._task_statement(filters)

        tasks = list(
            self.db.scalars(
                task_statement.order_by(
                    Task.created_at.desc(),
                )
            ).all()
        )

        workflow_statement = self._workflow_statement(filters)

        workflow_records = self.db.execute(
            workflow_statement.order_by(
                WorkflowExecution.started_at.desc(),
            ),
        ).all()

        rows: list[list[Any]] = []

        for task in tasks:
            rows.append(
                [
                    "TASK",
                    task.id,
                    task.title,
                    task.status.value,
                    task.priority.value,
                    task.sla_status.value if task.sla_status is not None else None,
                    task.assigned_to,
                    task.created_at,
                    task.due_date,
                    task.completed_at,
                ]
            )

        for execution, workflow in workflow_records:
            rows.append(
                [
                    "WORKFLOW",
                    execution.id,
                    workflow.name,
                    execution.status.value,
                    None,
                    (
                        execution.sla_status.value
                        if execution.sla_status is not None
                        else None
                    ),
                    execution.started_by,
                    execution.started_at,
                    execution.due_date,
                    execution.completed_at,
                ]
            )

        return ReportTable(
            title="Operational Performance Report",
            columns=[
                "Record Type",
                "Record ID",
                "Task / Workflow",
                "Status",
                "Priority",
                "SLA Status",
                "Assigned / Started By",
                "Created / Started At",
                "Due Date",
                "Completed At",
            ],
            rows=rows,
        )
