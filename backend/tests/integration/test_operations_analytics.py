from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from app.analytics.models.operations_daily import OperationsAnalyticsDaily
from app.models.task import Task
from app.models.workflow import Workflow, WorkflowExecution
from app.utils.enums import (
    SLAStatus,
    TaskStatus,
    UserRole,
    WorkflowExecutionStatus,
    WorkflowStatus,
)
from tests.helpers import authenticate_client


def make_operations_snapshot(
    snapshot_date: date,
    *,
    workflows_started: int,
    workflows_completed: int,
    workflows_failed: int,
    tasks_completed: int,
    tasks_completed_within_sla: int,
    tasks_completed_breached_sla: int,
    active_workflows: int,
    open_tasks: int,
    overdue_tasks: int,
    total_tasks: int,
    total_workflows: int,
) -> OperationsAnalyticsDaily:
    return OperationsAnalyticsDaily(
        snapshot_date=snapshot_date,
        ending_total_tasks=total_tasks,
        tasks_created_during_day=0,
        ending_open_tasks=open_tasks,
        ending_total_completed_tasks=(total_tasks - open_tasks),
        tasks_completed_during_day=tasks_completed,
        ending_overdue_tasks=overdue_tasks,
        ending_tasks_sla_within_target=0,
        ending_tasks_sla_approaching_deadline=0,
        ending_tasks_sla_breached=0,
        ending_tasks_sla_completed_on_time=0,
        tasks_completed_within_sla_during_day=(tasks_completed_within_sla),
        tasks_completed_breached_sla_during_day=(tasks_completed_breached_sla),
        ending_total_workflows=total_workflows,
        workflows_started_during_day=workflows_started,
        ending_active_workflows=active_workflows,
        ending_total_completed_workflows=(workflows_completed),
        workflows_completed_during_day=(workflows_completed),
        ending_total_failed_workflows=workflows_failed,
        workflows_failed_during_day=workflows_failed,
        ending_workflows_sla_within_target=0,
        ending_workflows_sla_approaching_deadline=0,
        ending_workflows_sla_breached=0,
        ending_workflows_sla_completed_on_time=0,
        workflows_completed_within_sla_during_day=0,
        workflows_completed_breached_sla_during_day=0,
    )


def test_operations_performance_returns_accurate_metrics(
    client,
    db_session,
    create_test_tenant,
    create_test_user,
    cleanup_analytics_snapshots,
    cleanup_tasks,
    cleanup_workflows,
    cleanup_workflow_executions,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "operations-analytics-admin@example.com",
    )

    reviewer = create_test_user(
        UserRole.REVIEWER,
        "operations-analytics-reviewer@example.com",
    )

    tenant = create_test_tenant(
        name="Tenant B",
        code=f"TENANT-B-{uuid4().hex[:6].upper()}",
    )

    admin.department = "Operations"
    reviewer.department = "Compliance"

    db_session.merge(admin)
    db_session.merge(reviewer)

    authenticate_client(
        client,
        admin,
    )

    db_session.add_all(
        [
            make_operations_snapshot(
                date(2029, 12, 31),
                workflows_started=1,
                workflows_completed=1,
                workflows_failed=0,
                tasks_completed=1,
                tasks_completed_within_sla=1,
                tasks_completed_breached_sla=0,
                active_workflows=2,
                open_tasks=3,
                overdue_tasks=1,
                total_tasks=4,
                total_workflows=3,
            ),
            make_operations_snapshot(
                date(2030, 1, 1),
                workflows_started=2,
                workflows_completed=1,
                workflows_failed=0,
                tasks_completed=1,
                tasks_completed_within_sla=1,
                tasks_completed_breached_sla=0,
                active_workflows=3,
                open_tasks=4,
                overdue_tasks=1,
                total_tasks=6,
                total_workflows=5,
            ),
            make_operations_snapshot(
                date(2030, 1, 2),
                workflows_started=2,
                workflows_completed=1,
                workflows_failed=1,
                tasks_completed=2,
                tasks_completed_within_sla=1,
                tasks_completed_breached_sla=1,
                active_workflows=2,
                open_tasks=3,
                overdue_tasks=2,
                total_tasks=7,
                total_workflows=6,
            ),
        ]
    )

    workflow = Workflow(
        tenant_id=tenant.id,
        name="Operations Analytics Test Workflow",
        description="Operations analytics test",
        status=WorkflowStatus.ACTIVE,
    )

    db_session.add(workflow)
    db_session.flush()

    workflow_completed_1 = WorkflowExecution(
        workflow_id=workflow.id,
        entity_type="CUSTOMER",
        entity_id=admin.id,
        status=WorkflowExecutionStatus.COMPLETED,
        started_by=admin.id,
        started_at=datetime(
            2030,
            1,
            1,
            8,
            0,
            tzinfo=timezone.utc,
        ),
        completed_at=datetime(
            2030,
            1,
            1,
            12,
            0,
            tzinfo=timezone.utc,
        ),
    )

    workflow_completed_2 = WorkflowExecution(
        workflow_id=workflow.id,
        entity_type="CUSTOMER",
        entity_id=reviewer.id,
        status=WorkflowExecutionStatus.COMPLETED,
        started_by=admin.id,
        started_at=datetime(
            2030,
            1,
            2,
            8,
            0,
            tzinfo=timezone.utc,
        ),
        completed_at=datetime(
            2030,
            1,
            2,
            10,
            0,
            tzinfo=timezone.utc,
        ),
    )

    db_session.add_all(
        [
            workflow_completed_1,
            workflow_completed_2,
        ]
    )

    db_session.flush()

    task_1_created = datetime(
        2030,
        1,
        1,
        8,
        0,
        tzinfo=timezone.utc,
    )

    task_1_completed = datetime(
        2030,
        1,
        1,
        10,
        0,
        tzinfo=timezone.utc,
    )

    task_2_created = datetime(
        2030,
        1,
        2,
        8,
        0,
        tzinfo=timezone.utc,
    )

    task_2_completed = datetime(
        2030,
        1,
        2,
        12,
        0,
        tzinfo=timezone.utc,
    )

    task_3_created = datetime(
        2030,
        1,
        2,
        8,
        0,
        tzinfo=timezone.utc,
    )

    task_3_completed = datetime(
        2030,
        1,
        2,
        13,
        0,
        tzinfo=timezone.utc,
    )

    db_session.add_all(
        [
            Task(
                title="Completed task 1",
                assigned_to=reviewer.id,
                status=TaskStatus.COMPLETED,
                sla_status=SLAStatus.COMPLETED,
                created_at=task_1_created,
                completed_at=task_1_completed,
                due_date=task_1_completed + timedelta(hours=1),
            ),
            Task(
                title="Completed task 2",
                assigned_to=reviewer.id,
                status=TaskStatus.COMPLETED,
                sla_status=SLAStatus.COMPLETED,
                created_at=task_2_created,
                completed_at=task_2_completed,
                due_date=task_2_completed + timedelta(hours=1),
            ),
            Task(
                title="Completed task 3 breached",
                assigned_to=admin.id,
                status=TaskStatus.COMPLETED,
                sla_status=SLAStatus.BREACHED,
                created_at=task_3_created,
                completed_at=task_3_completed,
                due_date=datetime(
                    2030,
                    1,
                    2,
                    11,
                    0,
                    tzinfo=timezone.utc,
                ),
            ),
            Task(
                title="Open task",
                assigned_to=admin.id,
                status=TaskStatus.IN_PROGRESS,
                sla_status=SLAStatus.BREACHED,
                created_at=datetime(
                    2030,
                    1,
                    2,
                    7,
                    0,
                    tzinfo=timezone.utc,
                ),
                due_date=datetime(
                    2030,
                    1,
                    1,
                    7,
                    0,
                    tzinfo=timezone.utc,
                ),
            ),
        ]
    )

    db_session.commit()

    response = client.get(
        "/api/v1/analytics/operations-performance",
        params={
            "start_date": "2030-01-01",
            "end_date": "2030-01-02",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True

    data = body["data"]

    assert data["filters"]["start_date"] == "2030-01-01"
    assert data["filters"]["end_date"] == "2030-01-02"

    assert data["workflow"]["workflows_started_during_period"] == 4

    assert data["workflow"]["workflows_completed_during_period"] == 2

    assert data["workflow"]["workflows_failed_during_period"] == 1

    assert data["workflow"]["average_completion_time_hours"] == 3.0

    assert data["workflow"]["ending_active_workflows"] == 2

    assert data["tasks"]["tasks_completed_during_period"] == 3

    assert data["tasks"]["ending_open_tasks"] == 3
    assert data["tasks"]["ending_overdue_tasks"] == 2

    assert data["tasks"]["average_resolution_time_hours"] == 3.67

    assert data["sla"]["tasks_completed_within_sla_during_period"] == 2

    assert data["sla"]["tasks_completed_breached_sla_during_period"] == 1

    assert data["sla"]["sla_compliance_percentage"] == 66.67

    assert data["sla"]["sla_breaches_during_period"] == 1

    assert data["sla"]["ending_sla_breaches"] == 0

    assert data["sla"]["average_delay_hours"] == 2.0

    employees = {row["employee_id"]: row for row in data["tasks"]["employees"]}

    assert employees[str(reviewer.id)]["tasks_completed_during_period"] == 2

    assert employees[str(reviewer.id)]["average_resolution_time_hours"] == 3.0

    assert employees[str(admin.id)]["tasks_completed_during_period"] == 1


def test_operations_performance_returns_historical_comparison(
    client,
    db_session,
    create_test_user,
    cleanup_analytics_snapshots,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "operations-analytics-history@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    db_session.add_all(
        [
            make_operations_snapshot(
                date(2029, 12, 31),
                workflows_started=1,
                workflows_completed=1,
                workflows_failed=0,
                tasks_completed=1,
                tasks_completed_within_sla=1,
                tasks_completed_breached_sla=0,
                active_workflows=1,
                open_tasks=1,
                overdue_tasks=0,
                total_tasks=2,
                total_workflows=2,
            ),
            make_operations_snapshot(
                date(2030, 1, 1),
                workflows_started=2,
                workflows_completed=2,
                workflows_failed=0,
                tasks_completed=2,
                tasks_completed_within_sla=1,
                tasks_completed_breached_sla=1,
                active_workflows=1,
                open_tasks=2,
                overdue_tasks=1,
                total_tasks=4,
                total_workflows=4,
            ),
        ]
    )

    db_session.commit()

    response = client.get(
        "/api/v1/analytics/operations-performance",
        params={
            "start_date": "2030-01-01",
            "end_date": "2030-01-01",
        },
    )

    assert response.status_code == 200

    comparison = response.json()["data"]["historical_comparison"]

    assert comparison["previous_start_date"] == "2029-12-31"
    assert comparison["previous_end_date"] == "2029-12-31"

    assert comparison["workflows_completed_change_percentage"] == 100.0

    assert comparison["tasks_completed_change_percentage"] == 100.0

    assert comparison["sla_compliance_change_percentage_points"] == -50.0


def test_reviewer_cannot_access_operations_performance(
    client,
    create_test_user,
):
    reviewer = create_test_user(
        UserRole.REVIEWER,
        "operations-analytics-forbidden@example.com",
    )

    authenticate_client(
        client,
        reviewer,
    )

    response = client.get(
        "/api/v1/analytics/operations-performance",
    )

    assert response.status_code == 403


def test_auditor_can_access_operations_performance(
    client,
    create_test_user,
):
    auditor = create_test_user(
        UserRole.AUDITOR,
        "operations-analytics-auditor@example.com",
    )

    authenticate_client(
        client,
        auditor,
    )

    response = client.get(
        "/api/v1/analytics/operations-performance",
    )

    assert response.status_code == 200


def test_operations_performance_rejects_invalid_date_range(
    client,
    create_test_user,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "operations-analytics-invalid-date@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.get(
        "/api/v1/analytics/operations-performance",
        params={
            "start_date": "2030-02-10",
            "end_date": "2030-02-01",
        },
    )

    assert response.status_code == 400


def test_operations_performance_rejects_range_longer_than_366_days(
    client,
    create_test_user,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "operations-analytics-long-range@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.get(
        "/api/v1/analytics/operations-performance",
        params={
            "start_date": "2028-01-01",
            "end_date": "2030-01-01",
        },
    )

    assert response.status_code == 400
