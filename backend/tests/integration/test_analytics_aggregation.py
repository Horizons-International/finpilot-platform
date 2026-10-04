from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.analytics.models.compliance_daily import ComplianceAnalyticsDaily
from app.analytics.models.compliance_monthly import ComplianceAnalyticsMonthly
from app.analytics.models.customer_daily import CustomerAnalyticsDaily
from app.analytics.models.customer_monthly import CustomerAnalyticsMonthly
from app.analytics.models.operations_daily import OperationsAnalyticsDaily
from app.analytics.models.operations_monthly import OperationsAnalyticsMonthly
from app.analytics.services.aggregation_service import (
    AnalyticsAggregationService,
)
from app.models.aml_rule import AMLRule
from app.models.compliance_case import ComplianceCase
from app.models.customer import Customer
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.task import Task
from app.models.transaction_monitoring_result import (
    TransactionMonitoringResult,
)
from app.models.verification_case import IdentityVerificationCase
from app.models.workflow import Workflow, WorkflowExecution
from app.utils.enums import (
    AMLRuleSeverity,
    AMLRuleStatus,
    AMLRuleType,
    ComplianceCasePriority,
    ComplianceCaseStatus,
    ComplianceCaseType,
    CustomerRiskLevel,
    CustomerStatus,
    SLAStatus,
    TaskStatus,
    TransactionMonitoringOutcome,
    VerificationStatus,
    VerificationType,
    WorkflowExecutionStatus,
    WorkflowStatus,
)


@pytest.fixture
def cleanup_analytics_aggregations(db_session):
    existing_customer_daily = {
        row.snapshot_date for row in db_session.query(CustomerAnalyticsDaily).all()
    }

    existing_customer_monthly = {
        row.month_start for row in db_session.query(CustomerAnalyticsMonthly).all()
    }

    existing_compliance_daily = {
        row.snapshot_date for row in db_session.query(ComplianceAnalyticsDaily).all()
    }

    existing_compliance_monthly = {
        row.month_start for row in db_session.query(ComplianceAnalyticsMonthly).all()
    }

    existing_operations_daily = {
        row.snapshot_date for row in db_session.query(OperationsAnalyticsDaily).all()
    }

    existing_operations_monthly = {
        row.month_start for row in db_session.query(OperationsAnalyticsMonthly).all()
    }

    yield

    for row in db_session.query(CustomerAnalyticsDaily).all():
        if row.snapshot_date not in existing_customer_daily:
            db_session.delete(row)

    for row in db_session.query(CustomerAnalyticsMonthly).all():
        if row.month_start not in existing_customer_monthly:
            db_session.delete(row)

    for row in db_session.query(ComplianceAnalyticsDaily).all():
        if row.snapshot_date not in existing_compliance_daily:
            db_session.delete(row)

    for row in db_session.query(ComplianceAnalyticsMonthly).all():
        if row.month_start not in existing_compliance_monthly:
            db_session.delete(row)

    for row in db_session.query(OperationsAnalyticsDaily).all():
        if row.snapshot_date not in existing_operations_daily:
            db_session.delete(row)

    for row in db_session.query(OperationsAnalyticsMonthly).all():
        if row.month_start not in existing_operations_monthly:
            db_session.delete(row)

    db_session.commit()


def test_daily_aggregation_stores_event_metrics(
    db_session,
    cleanup_analytics_aggregations,
    cleanup_test_customers,
    cleanup_compliance_cases,
    cleanup_tasks,
    cleanup_workflows,
    cleanup_aml_rules,
    cleanup_transaction_monitoring_results,
):
    event_time = datetime(
        2030,
        1,
        15,
        12,
        0,
        tzinfo=timezone.utc,
    )

    customer = Customer(
        first_name="Analytics",
        last_name="Customer",
        email=f"analytics-{uuid4()}@example.com",
        phone_number="+249123456789",
        status=CustomerStatus.VERIFIED,
        created_at=event_time,
    )

    db_session.add(customer)
    db_session.flush()

    db_session.add(
        IdentityVerificationCase(
            customer_id=customer.id,
            verification_type=VerificationType.IDENTITY,
            status=VerificationStatus.APPROVED,
            completed_at=event_time,
            created_at=event_time - timedelta(days=1),
        )
    )

    db_session.add(
        ComplianceCase(
            customer_id=customer.id,
            case_type=ComplianceCaseType.CUSTOMER_REVIEW,
            priority=ComplianceCasePriority.HIGH,
            status=ComplianceCaseStatus.OPEN,
            created_at=event_time,
        )
    )

    db_session.add(
        CustomerRiskProfile(
            customer_id=customer.id,
            risk_level=CustomerRiskLevel.HIGH,
            risk_score=85,
            risk_category="HIGH_RISK",
            assessed_at=event_time,
            assessment_source="TEST",
        )
    )

    aml_rule = AMLRule(
        name=f"Analytics AML Rule {uuid4()}",
        rule_type=AMLRuleType.TRANSACTION,
        condition={
            "amount": {
                "greater_than": 10000,
            }
        },
        severity=AMLRuleSeverity.HIGH,
        status=AMLRuleStatus.ACTIVE,
    )

    db_session.add(aml_rule)
    db_session.flush()

    db_session.add(
        TransactionMonitoringResult(
            transaction_id=uuid4(),
            customer_id=customer.id,
            rule_id=aml_rule.id,
            country="Sudan",
            result=TransactionMonitoringOutcome.MATCHED,
            created_at=event_time,
        )
    )

    workflow = Workflow(
        name=f"Analytics Workflow {uuid4()}",
        description="Analytics aggregation test workflow.",
        status=WorkflowStatus.ACTIVE,
    )

    db_session.add(workflow)
    db_session.flush()

    workflow_completed = WorkflowExecution(
        workflow_id=workflow.id,
        entity_type="CUSTOMER",
        entity_id=customer.id,
        status=WorkflowExecutionStatus.COMPLETED,
        started_at=event_time - timedelta(hours=2),
        completed_at=event_time,
        due_date=event_time + timedelta(hours=2),
        sla_status=SLAStatus.COMPLETED,
    )

    db_session.add(workflow_completed)
    db_session.flush()

    task = Task(
        title="Analytics aggregation test task",
        status=TaskStatus.COMPLETED,
        workflow_execution_id=workflow_completed.id,
        created_at=event_time - timedelta(hours=1),
        completed_at=event_time,
        due_date=event_time + timedelta(hours=1),
        sla_status=SLAStatus.COMPLETED,
    )

    db_session.add(task)

    db_session.commit()

    service = AnalyticsAggregationService(
        db_session,
    )

    service.aggregate_daily(
        aggregation_date=date(
            2030,
            1,
            15,
        ),
    )

    customer_snapshot = db_session.get(
        CustomerAnalyticsDaily,
        date(2030, 1, 15),
    )

    compliance_snapshot = db_session.get(
        ComplianceAnalyticsDaily,
        date(2030, 1, 15),
    )

    operations_snapshot = db_session.get(
        OperationsAnalyticsDaily,
        date(2030, 1, 15),
    )

    assert customer_snapshot is not None
    assert compliance_snapshot is not None
    assert operations_snapshot is not None

    assert customer_snapshot.customers_registered_during_day == 1
    assert customer_snapshot.verification_approvals_during_day == 1

    assert compliance_snapshot.cases_created_during_day == 1
    assert compliance_snapshot.alerts_created_during_day == 1

    assert operations_snapshot.tasks_created_during_day == 1
    assert operations_snapshot.tasks_completed_during_day == 1
    assert operations_snapshot.tasks_completed_within_sla_during_day == 1

    assert operations_snapshot.workflows_started_during_day == 1
    assert operations_snapshot.workflows_completed_during_day == 1
    assert operations_snapshot.workflows_completed_within_sla_during_day == 1


def test_monthly_aggregation_uses_ending_state_and_monthly_activity(
    db_session,
    cleanup_analytics_aggregations,
):
    month_start = date(
        2030,
        1,
        1,
    )

    previous_customer = CustomerAnalyticsDaily(
        snapshot_date=date(
            2029,
            12,
            31,
        ),
        ending_total_customers=100,
        customers_registered_during_day=0,
        verification_approvals_during_day=0,
        ending_pending_verification_customers=10,
        ending_verified_customers=90,
        ending_suspended_customers=0,
        ending_rejected_customers=0,
    )

    db_session.add(previous_customer)

    for day_number in range(1, 32):
        ending_total_customers = 103 if day_number == 1 else 108

        db_session.add(
            CustomerAnalyticsDaily(
                snapshot_date=date(
                    2030,
                    1,
                    day_number,
                ),
                ending_total_customers=ending_total_customers,
                customers_registered_during_day=(
                    3 if day_number == 1 else 5 if day_number == 2 else 0
                ),
                verification_approvals_during_day=(
                    2 if day_number == 1 else 4 if day_number == 2 else 0
                ),
                ending_pending_verification_customers=12,
                ending_verified_customers=96,
                ending_suspended_customers=0,
                ending_rejected_customers=0,
            )
        )

        db_session.add(
            ComplianceAnalyticsDaily(
                snapshot_date=date(
                    2030,
                    1,
                    day_number,
                ),
                ending_total_cases=10,
                cases_created_during_day=1,
                ending_open_cases=4,
                ending_resolved_cases=3,
                ending_closed_cases=3,
                ending_total_alerts=20,
                alerts_created_during_day=2,
                ending_low_severity_alerts=5,
                ending_medium_severity_alerts=5,
                ending_high_severity_alerts=6,
                ending_critical_severity_alerts=4,
                ending_low_risk_customers=50,
                ending_medium_risk_customers=30,
                ending_high_risk_customers=15,
                ending_critical_risk_customers=5,
            )
        )

        db_session.add(
            OperationsAnalyticsDaily(
                snapshot_date=date(
                    2030,
                    1,
                    day_number,
                ),
                ending_total_tasks=100,
                tasks_created_during_day=3,
                ending_open_tasks=20,
                ending_total_completed_tasks=80,
                tasks_completed_during_day=2,
                ending_overdue_tasks=5,
                ending_tasks_sla_within_target=70,
                ending_tasks_sla_approaching_deadline=10,
                ending_tasks_sla_breached=5,
                ending_tasks_sla_completed_on_time=80,
                tasks_completed_within_sla_during_day=1,
                tasks_completed_breached_sla_during_day=1,
                ending_total_workflows=50,
                workflows_started_during_day=2,
                ending_active_workflows=10,
                ending_total_completed_workflows=35,
                workflows_completed_during_day=1,
                ending_total_failed_workflows=5,
                workflows_failed_during_day=0,
                ending_workflows_sla_within_target=40,
                ending_workflows_sla_approaching_deadline=5,
                ending_workflows_sla_breached=5,
                ending_workflows_sla_completed_on_time=35,
                workflows_completed_within_sla_during_day=1,
                workflows_completed_breached_sla_during_day=0,
            )
        )

    db_session.commit()

    service = AnalyticsAggregationService(
        db_session,
    )

    service.aggregate_monthly(
        month_start=month_start,
    )

    customer_month = db_session.get(
        CustomerAnalyticsMonthly,
        month_start,
    )

    compliance_month = db_session.get(
        ComplianceAnalyticsMonthly,
        month_start,
    )

    operations_month = db_session.get(
        OperationsAnalyticsMonthly,
        month_start,
    )

    assert customer_month is not None
    assert compliance_month is not None
    assert operations_month is not None

    assert customer_month.ending_total_customers == 108
    assert customer_month.customers_registered_during_month == 8
    assert customer_month.verification_approvals_during_month == 6
    assert customer_month.customer_growth == 8

    assert compliance_month.cases_created_during_month == 31
    assert compliance_month.alerts_created_during_month == 62
    assert compliance_month.ending_open_cases == 4
    assert compliance_month.ending_high_risk_customers == 15
    assert compliance_month.ending_critical_risk_customers == 5

    assert operations_month.tasks_created_during_month == 93
    assert operations_month.tasks_completed_during_month == 62
    assert operations_month.tasks_completed_within_sla_during_month == 31
    assert operations_month.tasks_completed_breached_sla_during_month == 31

    assert operations_month.workflows_started_during_month == 62
    assert operations_month.workflows_completed_during_month == 31
    assert operations_month.workflows_failed_during_month == 0
    assert operations_month.workflows_completed_within_sla_during_month == 31


def test_daily_aggregation_is_idempotent(
    db_session,
    cleanup_analytics_aggregations,
):
    target_date = date(
        2030,
        2,
        1,
    )

    service = AnalyticsAggregationService(
        db_session,
    )

    service.aggregate_daily(
        aggregation_date=target_date,
    )

    service.aggregate_daily(
        aggregation_date=target_date,
    )

    customer_rows = (
        db_session.query(CustomerAnalyticsDaily)
        .filter(
            CustomerAnalyticsDaily.snapshot_date == target_date,
        )
        .all()
    )

    compliance_rows = (
        db_session.query(ComplianceAnalyticsDaily)
        .filter(
            ComplianceAnalyticsDaily.snapshot_date == target_date,
        )
        .all()
    )

    operations_rows = (
        db_session.query(OperationsAnalyticsDaily)
        .filter(
            OperationsAnalyticsDaily.snapshot_date == target_date,
        )
        .all()
    )

    assert len(customer_rows) == 1
    assert len(compliance_rows) == 1
    assert len(operations_rows) == 1


def test_monthly_aggregation_is_idempotent(
    db_session,
    cleanup_analytics_aggregations,
):
    month_start = date(
        2030,
        3,
        1,
    )

    for day_number in range(1, 32):
        db_session.add(
            CustomerAnalyticsDaily(
                snapshot_date=date(
                    2030,
                    3,
                    day_number,
                ),
                ending_total_customers=10,
                customers_registered_during_day=1,
                verification_approvals_during_day=0,
                ending_pending_verification_customers=1,
                ending_verified_customers=9,
                ending_suspended_customers=0,
                ending_rejected_customers=0,
            )
        )

        db_session.add(
            ComplianceAnalyticsDaily(
                snapshot_date=date(
                    2030,
                    3,
                    day_number,
                ),
                ending_total_cases=1,
                cases_created_during_day=1,
                ending_open_cases=1,
                ending_resolved_cases=0,
                ending_closed_cases=0,
                ending_total_alerts=1,
                alerts_created_during_day=1,
                ending_low_severity_alerts=1,
                ending_medium_severity_alerts=0,
                ending_high_severity_alerts=0,
                ending_critical_severity_alerts=0,
                ending_low_risk_customers=10,
                ending_medium_risk_customers=0,
                ending_high_risk_customers=0,
                ending_critical_risk_customers=0,
            )
        )

        db_session.add(
            OperationsAnalyticsDaily(
                snapshot_date=date(
                    2030,
                    3,
                    day_number,
                ),
                ending_total_tasks=1,
                tasks_created_during_day=1,
                ending_open_tasks=1,
                ending_total_completed_tasks=0,
                tasks_completed_during_day=0,
                ending_overdue_tasks=0,
                ending_tasks_sla_within_target=1,
                ending_tasks_sla_approaching_deadline=0,
                ending_tasks_sla_breached=0,
                ending_tasks_sla_completed_on_time=0,
                tasks_completed_within_sla_during_day=0,
                tasks_completed_breached_sla_during_day=0,
                ending_total_workflows=1,
                workflows_started_during_day=1,
                ending_active_workflows=1,
                ending_total_completed_workflows=0,
                workflows_completed_during_day=0,
                ending_total_failed_workflows=0,
                workflows_failed_during_day=0,
                ending_workflows_sla_within_target=1,
                ending_workflows_sla_approaching_deadline=0,
                ending_workflows_sla_breached=0,
                ending_workflows_sla_completed_on_time=0,
                workflows_completed_within_sla_during_day=0,
                workflows_completed_breached_sla_during_day=0,
            )
        )

    db_session.commit()

    service = AnalyticsAggregationService(
        db_session,
    )

    service.aggregate_monthly(
        month_start=month_start,
    )

    service.aggregate_monthly(
        month_start=month_start,
    )

    customer_rows = (
        db_session.query(CustomerAnalyticsMonthly)
        .filter(
            CustomerAnalyticsMonthly.month_start == month_start,
        )
        .all()
    )

    compliance_rows = (
        db_session.query(ComplianceAnalyticsMonthly)
        .filter(
            ComplianceAnalyticsMonthly.month_start == month_start,
        )
        .all()
    )

    operations_rows = (
        db_session.query(OperationsAnalyticsMonthly)
        .filter(
            OperationsAnalyticsMonthly.month_start == month_start,
        )
        .all()
    )

    assert len(customer_rows) == 1
    assert len(compliance_rows) == 1
    assert len(operations_rows) == 1
