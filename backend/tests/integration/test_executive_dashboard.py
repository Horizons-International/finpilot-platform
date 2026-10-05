from datetime import date, datetime, timedelta, timezone

from app.analytics.models.compliance_daily import ComplianceAnalyticsDaily
from app.analytics.models.customer_daily import CustomerAnalyticsDaily
from app.analytics.models.operations_daily import OperationsAnalyticsDaily
from app.models.task import Task
from app.utils.enums import (
    SLAStatus,
    TaskStatus,
    UserRole,
)


def authenticate_client(client, user):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": user.email,
            "password": "Password123!",
        },
    )

    assert response.status_code == 200

    token = response.json()["data"]["access_token"]

    client.headers.update(
        {
            "Authorization": f"Bearer {token}",
        }
    )


def test_executive_dashboard_returns_dashboard_data(
    client,
    db_session,
    create_test_user,
    cleanup_analytics_snapshots,
    cleanup_tasks,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "executive-dashboard-admin@example.com",
    )

    reviewer = create_test_user(
        UserRole.REVIEWER,
        "executive-dashboard-reviewer@example.com",
    )

    reviewer.department = "Compliance"
    db_session.merge(reviewer)
    db_session.commit()

    authenticate_client(
        client,
        admin,
    )

    customer_rows = [
        CustomerAnalyticsDaily(
            snapshot_date=date(2030, 1, 1),
            ending_total_customers=100,
            customers_registered_during_day=5,
            verification_approvals_during_day=3,
            ending_pending_verification_customers=20,
            ending_verified_customers=70,
            ending_suspended_customers=5,
            ending_rejected_customers=5,
        ),
        CustomerAnalyticsDaily(
            snapshot_date=date(2030, 1, 2),
            ending_total_customers=110,
            customers_registered_during_day=10,
            verification_approvals_during_day=7,
            ending_pending_verification_customers=18,
            ending_verified_customers=82,
            ending_suspended_customers=5,
            ending_rejected_customers=5,
        ),
    ]

    compliance_row = ComplianceAnalyticsDaily(
        snapshot_date=date(2030, 1, 2),
        ending_total_cases=40,
        cases_created_during_day=4,
        ending_open_cases=12,
        ending_resolved_cases=15,
        ending_closed_cases=13,
        ending_total_alerts=25,
        alerts_created_during_day=3,
        ending_low_severity_alerts=8,
        ending_medium_severity_alerts=7,
        ending_high_severity_alerts=6,
        ending_critical_severity_alerts=4,
        ending_low_risk_customers=60,
        ending_medium_risk_customers=30,
        ending_high_risk_customers=15,
        ending_critical_risk_customers=5,
    )

    operations_row = OperationsAnalyticsDaily(
        snapshot_date=date(2030, 1, 2),
        ending_total_tasks=50,
        tasks_created_during_day=6,
        ending_open_tasks=20,
        ending_total_completed_tasks=30,
        tasks_completed_during_day=5,
        ending_overdue_tasks=3,
        ending_tasks_sla_within_target=10,
        ending_tasks_sla_approaching_deadline=5,
        ending_tasks_sla_breached=3,
        ending_tasks_sla_completed_on_time=32,
        tasks_completed_within_sla_during_day=4,
        tasks_completed_breached_sla_during_day=1,
        ending_total_workflows=15,
        workflows_started_during_day=3,
        ending_active_workflows=5,
        ending_total_completed_workflows=9,
        workflows_completed_during_day=2,
        ending_total_failed_workflows=1,
        workflows_failed_during_day=1,
        ending_workflows_sla_within_target=4,
        ending_workflows_sla_approaching_deadline=2,
        ending_workflows_sla_breached=1,
        ending_workflows_sla_completed_on_time=8,
        workflows_completed_within_sla_during_day=2,
        workflows_completed_breached_sla_during_day=0,
    )

    db_session.add_all(
        [
            *customer_rows,
            compliance_row,
            operations_row,
        ]
    )

    dashboard_date_1 = datetime(
        2030,
        1,
        1,
        10,
        0,
        tzinfo=timezone.utc,
    )

    dashboard_date_2 = datetime(
        2030,
        1,
        2,
        10,
        0,
        tzinfo=timezone.utc,
    )

    db_session.add_all(
        [
            Task(
                title="Executive dashboard completed SLA 1",
                assigned_to=reviewer.id,
                status=TaskStatus.COMPLETED,
                sla_status=SLAStatus.COMPLETED,
                created_at=dashboard_date_1,
                completed_at=dashboard_date_1 + timedelta(hours=2),
            ),
            Task(
                title="Executive dashboard completed SLA 2",
                assigned_to=reviewer.id,
                status=TaskStatus.COMPLETED,
                sla_status=SLAStatus.COMPLETED,
                created_at=dashboard_date_1,
                completed_at=dashboard_date_1 + timedelta(hours=3),
            ),
            Task(
                title="Executive dashboard completed SLA 3",
                assigned_to=reviewer.id,
                status=TaskStatus.COMPLETED,
                sla_status=SLAStatus.COMPLETED,
                created_at=dashboard_date_2,
                completed_at=dashboard_date_2 + timedelta(hours=2),
            ),
            Task(
                title="Executive dashboard completed SLA 4",
                assigned_to=reviewer.id,
                status=TaskStatus.COMPLETED,
                sla_status=SLAStatus.COMPLETED,
                created_at=dashboard_date_2,
                completed_at=dashboard_date_2 + timedelta(hours=3),
            ),
            Task(
                title="Executive dashboard completed after SLA",
                assigned_to=reviewer.id,
                status=TaskStatus.COMPLETED,
                sla_status=SLAStatus.BREACHED,
                created_at=dashboard_date_2,
                completed_at=dashboard_date_2 + timedelta(hours=10),
            ),
        ]
    )

    db_session.commit()

    response = client.get(
        "/api/v1/analytics/executive-dashboard",
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

    assert data["customer_overview"]["ending_total_customers"] == 110
    assert data["customer_overview"]["customer_growth"] == 10
    assert data["customer_overview"]["growth_trend"][0]["ending_total_customers"] == 100
    assert (
        data["customer_overview"]["verification_status"]["ending_verified_customers"]
        == 82
    )

    assert data["compliance_overview"]["ending_open_cases"] == 12
    assert (
        data["compliance_overview"]["risk_distribution"]["ending_high_risk_customers"]
        == 15
    )
    assert (
        data["compliance_overview"]["aml_alerts"]["ending_critical_severity_alerts"]
        == 4
    )

    assert (
        data["operations_overview"]["workflow_status"]["ending_active_workflows"] == 5
    )

    assert (
        data["operations_overview"]["sla_performance"]["task_sla_compliance_percentage"]
        == 80.0
    )


def test_executive_dashboard_rejects_invalid_date_range(
    client,
    create_test_user,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "executive-dashboard-invalid-date@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.get(
        "/api/v1/analytics/executive-dashboard",
        params={
            "start_date": "2030-02-10",
            "end_date": "2030-02-01",
        },
    )

    assert response.status_code == 400


def test_executive_dashboard_filters_team_workload_by_department(
    client,
    db_session,
    create_test_user,
    cleanup_tasks,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "executive-dashboard-department-admin@example.com",
    )

    reviewer = create_test_user(
        UserRole.REVIEWER,
        "executive-dashboard-department-reviewer@example.com",
    )

    reviewer.department = "Compliance"
    db_session.merge(reviewer)

    operations_user = create_test_user(
        UserRole.REVIEWER,
        "executive-dashboard-department-operations@example.com",
    )

    operations_user.department = "Operations"
    db_session.merge(operations_user)

    db_session.commit()

    authenticate_client(
        client,
        admin,
    )

    db_session.add_all(
        [
            Task(
                title="Compliance workload",
                assigned_to=reviewer.id,
                status=TaskStatus.IN_PROGRESS,
            ),
            Task(
                title="Operations workload",
                assigned_to=operations_user.id,
                status=TaskStatus.IN_PROGRESS,
            ),
        ]
    )

    db_session.commit()

    response = client.get(
        "/api/v1/analytics/executive-dashboard",
        params={
            "department": "Compliance",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["filters"]["department"] == "Compliance"

    workload = data["operations_overview"]["team_workload"]

    assert len(workload) == 1
    assert workload[0]["team"] == "Compliance"
    assert workload[0]["open_tasks"] == 1


def test_reviewer_cannot_access_executive_dashboard(
    client,
    create_test_user,
):
    reviewer = create_test_user(
        UserRole.REVIEWER,
        "executive-dashboard-forbidden-reviewer@example.com",
    )

    authenticate_client(
        client,
        reviewer,
    )

    response = client.get(
        "/api/v1/analytics/executive-dashboard",
    )

    assert response.status_code == 403


def test_executive_dashboard_returns_empty_trend_when_no_snapshots_exist(
    client,
    create_test_user,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "executive-dashboard-empty@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.get(
        "/api/v1/analytics/executive-dashboard",
        params={
            "start_date": "2040-01-01",
            "end_date": "2040-01-10",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["customer_overview"]["ending_total_customers"] == 0
    assert data["customer_overview"]["growth_trend"] == []

    assert data["compliance_overview"]["ending_open_cases"] == 0

    assert (
        data["operations_overview"]["workflow_status"]["ending_active_workflows"] == 0
    )
