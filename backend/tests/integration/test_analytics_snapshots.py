from datetime import datetime, timedelta, timezone

from app.analytics.models.compliance_daily import ComplianceAnalyticsDaily
from app.analytics.models.customer_daily import CustomerAnalyticsDaily
from app.analytics.models.operations_daily import OperationsAnalyticsDaily
from app.analytics.services.snapshot_service import AnalyticsSnapshotService
from app.models.aml_rule import AMLRule
from app.models.compliance_case import ComplianceCase
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.task import Task
from app.models.transaction_monitoring_result import (
    TransactionMonitoringResult,
)
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
    UserRole,
    WorkflowExecutionStatus,
    WorkflowStatus,
)


def test_capture_snapshot_creates_customer_compliance_and_operations_rows(
    db_session,
    create_test_customer,
    create_test_user,
    cleanup_test_customers,
    cleanup_aml_rules,
    cleanup_transaction_monitoring_results,
    cleanup_compliance_cases,
    cleanup_tasks,
    cleanup_workflows,
    cleanup_analytics_snapshots,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="analytics-admin@example.com",
    )

    as_of = datetime(
        2026,
        10,
        4,
        12,
        0,
        tzinfo=timezone.utc,
    )

    old_customer = create_test_customer(
        status=CustomerStatus.VERIFIED,
        created_at=as_of - timedelta(days=10),
    )

    new_customer = create_test_customer(
        status=CustomerStatus.PENDING_VERIFICATION,
        created_at=as_of - timedelta(hours=1),
    )

    risk_customer = create_test_customer(
        status=CustomerStatus.VERIFIED,
        created_at=as_of - timedelta(hours=2),
    )

    db_session.add(
        CustomerRiskProfile(
            customer_id=risk_customer.id,
            risk_level=CustomerRiskLevel.HIGH,
            risk_score=85,
            risk_category="HIGH_RISK",
            assessed_at=as_of - timedelta(hours=1),
            assessment_source="TEST",
        )
    )

    db_session.add(
        ComplianceCase(
            customer_id=risk_customer.id,
            case_type=ComplianceCaseType.CUSTOMER_REVIEW,
            priority=ComplianceCasePriority.HIGH,
            status=ComplianceCaseStatus.OPEN,
            assigned_to=admin.id,
            created_at=as_of - timedelta(hours=1),
        )
    )

    aml_rule = AMLRule(
        name="Analytics AML Rule",
        rule_type=AMLRuleType.TRANSACTION,
        condition={"amount": {"greater_than": 10000}},
        severity=AMLRuleSeverity.HIGH,
        status=AMLRuleStatus.ACTIVE,
    )

    db_session.add(aml_rule)
    db_session.flush()

    db_session.add(
        TransactionMonitoringResult(
            transaction_id=old_customer.id,
            customer_id=risk_customer.id,
            rule_id=aml_rule.id,
            country="Sudan",
            result=TransactionMonitoringOutcome.MATCHED,
            created_at=as_of - timedelta(hours=3),
        )
    )

    workflow = Workflow(
        name="Analytics Workflow",
        description="Analytics test workflow",
        status=WorkflowStatus.ACTIVE,
    )

    db_session.add(workflow)
    db_session.flush()

    active_execution = WorkflowExecution(
        workflow_id=workflow.id,
        entity_type="CUSTOMER",
        entity_id=new_customer.id,
        status=WorkflowExecutionStatus.IN_PROGRESS,
        started_by=admin.id,
        started_at=as_of - timedelta(hours=3),
        due_date=as_of + timedelta(hours=3),
        sla_status=SLAStatus.WITHIN_SLA,
    )

    completed_execution = WorkflowExecution(
        workflow_id=workflow.id,
        entity_type="CUSTOMER",
        entity_id=old_customer.id,
        status=WorkflowExecutionStatus.COMPLETED,
        started_by=admin.id,
        started_at=as_of - timedelta(days=1),
        due_date=as_of - timedelta(hours=2),
        completed_at=as_of - timedelta(hours=3),
        sla_status=SLAStatus.COMPLETED,
    )

    failed_execution = WorkflowExecution(
        workflow_id=workflow.id,
        entity_type="CUSTOMER",
        entity_id=risk_customer.id,
        status=WorkflowExecutionStatus.FAILED,
        started_by=admin.id,
        started_at=as_of - timedelta(days=2),
        due_date=as_of - timedelta(days=1),
        completed_at=as_of - timedelta(hours=5),
        sla_status=SLAStatus.BREACHED,
    )

    db_session.add_all(
        [
            active_execution,
            completed_execution,
            failed_execution,
        ]
    )
    db_session.flush()

    db_session.add(
        Task(
            title="Analytics open task",
            status=TaskStatus.IN_PROGRESS,
            assigned_to=admin.id,
            due_date=as_of + timedelta(hours=2),
            sla_status=SLAStatus.WITHIN_SLA,
            workflow_execution_id=active_execution.id,
            created_at=as_of - timedelta(hours=2),
        )
    )

    db_session.add(
        Task(
            title="Analytics overdue task",
            status=TaskStatus.ASSIGNED,
            assigned_to=admin.id,
            due_date=as_of - timedelta(hours=1),
            sla_status=SLAStatus.BREACHED,
            created_at=as_of - timedelta(hours=4),
        )
    )

    db_session.add(
        Task(
            title="Analytics completed task",
            status=TaskStatus.COMPLETED,
            assigned_to=admin.id,
            due_date=as_of - timedelta(hours=3),
            completed_at=as_of - timedelta(hours=4),
            sla_status=SLAStatus.COMPLETED,
            created_at=as_of - timedelta(days=1),
        )
    )

    db_session.commit()

    service = AnalyticsSnapshotService(db_session)

    customer_snapshot, compliance_snapshot, operations_snapshot = (
        service.capture_snapshot(
            as_of=as_of,
        )
    )

    assert customer_snapshot.snapshot_date == as_of.date()
    assert customer_snapshot.customers_registered_during_day >= 2
    assert customer_snapshot.ending_pending_verification_customers >= 1
    assert customer_snapshot.ending_verified_customers >= 2

    assert compliance_snapshot.snapshot_date == as_of.date()
    assert compliance_snapshot.ending_total_cases >= 1
    assert compliance_snapshot.ending_open_cases >= 1
    assert compliance_snapshot.ending_total_alerts >= 1
    assert compliance_snapshot.ending_high_severity_alerts >= 1
    assert compliance_snapshot.ending_high_risk_customers >= 1

    assert operations_snapshot.snapshot_date == as_of.date()
    assert operations_snapshot.ending_total_tasks >= 3
    assert operations_snapshot.ending_open_tasks >= 2
    assert operations_snapshot.ending_total_completed_tasks >= 1
    assert operations_snapshot.ending_overdue_tasks >= 1
    assert operations_snapshot.ending_tasks_sla_within_target >= 1
    assert operations_snapshot.ending_tasks_sla_breached >= 1
    assert operations_snapshot.ending_tasks_sla_completed_on_time >= 1

    assert operations_snapshot.ending_total_workflows >= 3
    assert operations_snapshot.ending_active_workflows >= 1
    assert operations_snapshot.ending_total_completed_workflows >= 1
    assert operations_snapshot.ending_total_failed_workflows >= 1
    assert operations_snapshot.ending_workflows_sla_within_target >= 1
    assert operations_snapshot.ending_workflows_sla_breached >= 1
    assert operations_snapshot.ending_workflows_sla_completed_on_time >= 1


def test_capture_snapshot_is_idempotent_for_same_day(
    db_session,
    cleanup_analytics_snapshots,
):
    as_of = datetime(
        2026,
        10,
        4,
        9,
        0,
        tzinfo=timezone.utc,
    )

    service = AnalyticsSnapshotService(db_session)

    service.capture_snapshot(
        as_of=as_of,
    )

    first_customer = db_session.get(
        CustomerAnalyticsDaily,
        as_of.date(),
    )

    first_compliance = db_session.get(
        ComplianceAnalyticsDaily,
        as_of.date(),
    )

    first_operations = db_session.get(
        OperationsAnalyticsDaily,
        as_of.date(),
    )

    assert first_customer is not None
    assert first_compliance is not None
    assert first_operations is not None

    service.capture_snapshot(
        as_of=as_of + timedelta(hours=2),
    )

    customer_rows = (
        db_session.query(CustomerAnalyticsDaily)
        .filter(
            CustomerAnalyticsDaily.snapshot_date == as_of.date(),
        )
        .all()
    )

    compliance_rows = (
        db_session.query(ComplianceAnalyticsDaily)
        .filter(
            ComplianceAnalyticsDaily.snapshot_date == as_of.date(),
        )
        .all()
    )

    operations_rows = (
        db_session.query(OperationsAnalyticsDaily)
        .filter(
            OperationsAnalyticsDaily.snapshot_date == as_of.date(),
        )
        .all()
    )

    assert len(customer_rows) == 1
    assert len(compliance_rows) == 1
    assert len(operations_rows) == 1


def test_different_days_are_preserved_as_history(
    db_session,
    cleanup_analytics_snapshots,
):
    first_day = datetime(
        2026,
        10,
        2,
        12,
        0,
        tzinfo=timezone.utc,
    )

    second_day = datetime(
        2026,
        10,
        3,
        12,
        0,
        tzinfo=timezone.utc,
    )

    service = AnalyticsSnapshotService(db_session)

    service.capture_snapshot(
        as_of=first_day,
    )

    service.capture_snapshot(
        as_of=second_day,
    )

    customer_snapshots = (
        db_session.query(CustomerAnalyticsDaily)
        .order_by(
            CustomerAnalyticsDaily.snapshot_date,
        )
        .all()
    )

    compliance_snapshots = (
        db_session.query(ComplianceAnalyticsDaily)
        .order_by(
            ComplianceAnalyticsDaily.snapshot_date,
        )
        .all()
    )

    operations_snapshots = (
        db_session.query(OperationsAnalyticsDaily)
        .order_by(
            OperationsAnalyticsDaily.snapshot_date,
        )
        .all()
    )

    customer_dates = {row.snapshot_date for row in customer_snapshots}

    compliance_dates = {row.snapshot_date for row in compliance_snapshots}

    operations_dates = {row.snapshot_date for row in operations_snapshots}

    assert first_day.date() in customer_dates
    assert second_day.date() in customer_dates

    assert first_day.date() in compliance_dates
    assert second_day.date() in compliance_dates

    assert first_day.date() in operations_dates
    assert second_day.date() in operations_dates
