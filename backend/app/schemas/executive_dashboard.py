from datetime import date, datetime

from pydantic import BaseModel


class ExecutiveDashboardFilters(BaseModel):
    start_date: date
    end_date: date
    department: str | None = None


class CustomerGrowthTrendPoint(BaseModel):
    snapshot_date: date
    ending_total_customers: int
    customers_registered_during_day: int
    verification_approvals_during_day: int


class CustomerVerificationStatus(BaseModel):
    ending_pending_verification_customers: int
    ending_verified_customers: int
    ending_suspended_customers: int
    ending_rejected_customers: int


class CustomerOverview(BaseModel):
    ending_total_customers: int
    customer_growth: int
    customer_growth_percentage: float | None
    verification_status: CustomerVerificationStatus
    growth_trend: list[CustomerGrowthTrendPoint]


class ComplianceRiskDistribution(BaseModel):
    ending_low_risk_customers: int
    ending_medium_risk_customers: int
    ending_high_risk_customers: int
    ending_critical_risk_customers: int


class ComplianceAMLAlerts(BaseModel):
    ending_total_alerts: int
    ending_low_severity_alerts: int
    ending_medium_severity_alerts: int
    ending_high_severity_alerts: int
    ending_critical_severity_alerts: int


class ComplianceOverview(BaseModel):
    ending_total_cases: int
    ending_open_cases: int
    ending_resolved_cases: int
    ending_closed_cases: int
    risk_distribution: ComplianceRiskDistribution
    aml_alerts: ComplianceAMLAlerts


class WorkflowStatusOverview(BaseModel):
    ending_active_workflows: int
    ending_total_completed_workflows: int
    ending_total_failed_workflows: int


class SLAPerformance(BaseModel):
    tasks_completed_during_period: int
    tasks_completed_within_sla_during_period: int
    tasks_completed_breached_sla_during_period: int
    task_sla_compliance_percentage: float | None

    workflows_completed_during_period: int
    workflows_completed_within_sla_during_period: int
    workflows_completed_breached_sla_during_period: int
    workflow_sla_compliance_percentage: float | None


class TeamWorkload(BaseModel):
    team: str
    user_role: str | None
    open_tasks: int
    overdue_tasks: int


class OperationsOverview(BaseModel):
    workflow_status: WorkflowStatusOverview
    sla_performance: SLAPerformance
    team_workload: list[TeamWorkload]


class ExecutiveDashboardResponse(BaseModel):
    generated_at: datetime
    filters: ExecutiveDashboardFilters
    customer_overview: CustomerOverview
    compliance_overview: ComplianceOverview
    operations_overview: OperationsOverview
