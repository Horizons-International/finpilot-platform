from datetime import date, datetime

from pydantic import BaseModel


class DashboardCustomerMetrics(BaseModel):
    total_customers: int
    new_registrations: int
    pending_verification: int
    verified_customers: int


class DashboardWorkflowMetrics(BaseModel):
    active_workflows: int
    completed_workflows: int
    failed_workflows: int


class DashboardTaskMetrics(BaseModel):
    open_tasks: int
    completed_tasks: int
    overdue_tasks: int


class DashboardComplianceMetrics(BaseModel):
    open_cases: int
    high_risk_customers: int
    pending_reviews: int


class OperationsDashboardFilters(BaseModel):
    start_date: date | None
    end_date: date | None
    country: str | None
    user_role: str | None


class OperationsDashboardResponse(BaseModel):
    generated_at: datetime
    filters: OperationsDashboardFilters
    customers: DashboardCustomerMetrics
    workflows: DashboardWorkflowMetrics
    tasks: DashboardTaskMetrics
    compliance: DashboardComplianceMetrics
