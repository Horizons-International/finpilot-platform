from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


class OperationsAnalyticsFilters(BaseModel):
    start_date: date
    end_date: date


class WorkflowTrendPoint(BaseModel):
    snapshot_date: date
    workflows_started_during_day: int
    workflows_completed_during_day: int
    workflows_failed_during_day: int


class WorkflowPerformance(BaseModel):
    workflows_started_during_period: int
    workflows_completed_during_period: int
    workflows_failed_during_period: int
    average_completion_time_hours: float | None
    ending_active_workflows: int
    trend: list[WorkflowTrendPoint]


class EmployeeTaskPerformance(BaseModel):
    employee_id: UUID
    employee_name: str
    department: str | None
    user_role: str
    tasks_completed_during_period: int
    open_tasks_at_end: int
    overdue_tasks_at_end: int
    average_resolution_time_hours: float | None


class TaskPerformance(BaseModel):
    tasks_completed_during_period: int
    ending_open_tasks: int
    ending_overdue_tasks: int
    average_resolution_time_hours: float | None
    employees: list[EmployeeTaskPerformance]


class SLAPerformance(BaseModel):
    tasks_completed_during_period: int
    tasks_completed_within_sla_during_period: int
    tasks_completed_breached_sla_during_period: int
    sla_compliance_percentage: float | None
    sla_breaches_during_period: int
    ending_sla_breaches: int
    average_delay_hours: float | None


class HistoricalComparison(BaseModel):
    previous_start_date: date
    previous_end_date: date
    workflows_completed_change_percentage: float | None
    tasks_completed_change_percentage: float | None
    sla_compliance_change_percentage_points: float | None


class OperationsAnalyticsResponse(BaseModel):
    generated_at: datetime
    filters: OperationsAnalyticsFilters
    workflow: WorkflowPerformance
    tasks: TaskPerformance
    sla: SLAPerformance
    historical_comparison: HistoricalComparison
