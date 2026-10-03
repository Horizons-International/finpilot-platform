from datetime import datetime, timedelta, timezone

from app.models.compliance_case import ComplianceCase
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.task import Task
from app.models.verification_case import IdentityVerificationCase
from app.models.workflow import Workflow, WorkflowExecution
from app.utils.enums import (
    ComplianceCasePriority,
    ComplianceCaseStatus,
    ComplianceCaseType,
    CustomerRiskLevel,
    CustomerStatus,
    TaskStatus,
    UserRole,
    VerificationStatus,
    VerificationType,
    WorkflowExecutionStatus,
    WorkflowStatus,
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


def test_operations_dashboard_returns_accurate_metrics(
    client,
    db_session,
    create_test_user,
    create_test_customer,
    cleanup_test_customers,
    cleanup_workflows,
    cleanup_workflow_executions,
    cleanup_tasks,
    cleanup_compliance_cases,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "dashboard-admin@example.com",
    )

    reviewer = create_test_user(
        UserRole.REVIEWER,
        "dashboard-reviewer@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    customer_1 = create_test_customer(
        country_of_residence="Sudan",
        status=CustomerStatus.NEW,
    )

    customer_2 = create_test_customer(
        country_of_residence="Sudan",
        status=CustomerStatus.PENDING_VERIFICATION,
    )

    customer_3 = create_test_customer(
        country_of_residence="United Kingdom",
        status=CustomerStatus.VERIFIED,
    )

    customer_4 = create_test_customer(
        country_of_residence="Sudan",
        status=CustomerStatus.VERIFIED,
    )

    risk_profile = CustomerRiskProfile(
        customer_id=customer_4.id,
        risk_level=CustomerRiskLevel.HIGH,
        risk_score=85,
        risk_category="HIGH_RISK",
        assessed_at=datetime.now(timezone.utc),
        assessment_source="TEST",
    )

    db_session.add(risk_profile)

    verification_case = IdentityVerificationCase(
        customer_id=customer_2.id,
        verification_type=VerificationType.IDENTITY,
        status=VerificationStatus.UNDER_REVIEW,
        assigned_to=reviewer.id,
        assigned_at=datetime.now(timezone.utc),
    )

    db_session.add(verification_case)

    workflow = Workflow(
        name="Dashboard Test Workflow",
        description="Dashboard test workflow",
        status=WorkflowStatus.ACTIVE,
    )

    db_session.add(workflow)
    db_session.flush()

    workflow_active = WorkflowExecution(
        workflow_id=workflow.id,
        entity_type="customer",
        entity_id=customer_1.id,
        status=WorkflowExecutionStatus.IN_PROGRESS,
        started_by=admin.id,
    )

    workflow_completed = WorkflowExecution(
        workflow_id=workflow.id,
        entity_type="customer",
        entity_id=customer_2.id,
        status=WorkflowExecutionStatus.COMPLETED,
        started_by=reviewer.id,
    )

    workflow_failed = WorkflowExecution(
        workflow_id=workflow.id,
        entity_type="customer",
        entity_id=customer_3.id,
        status=WorkflowExecutionStatus.FAILED,
        started_by=reviewer.id,
    )

    db_session.add_all(
        [
            workflow_active,
            workflow_completed,
            workflow_failed,
        ]
    )
    db_session.flush()

    now = datetime.now(timezone.utc)

    open_task = Task(
        title="Dashboard open task",
        status=TaskStatus.IN_PROGRESS,
        assigned_to=reviewer.id,
        due_date=now + timedelta(days=1),
        workflow_execution_id=workflow_active.id,
    )

    overdue_task = Task(
        title="Dashboard overdue task",
        status=TaskStatus.ASSIGNED,
        assigned_to=reviewer.id,
        due_date=now - timedelta(days=1),
        workflow_execution_id=workflow_active.id,
    )

    completed_task = Task(
        title="Dashboard completed task",
        status=TaskStatus.COMPLETED,
        assigned_to=admin.id,
        due_date=now - timedelta(days=1),
    )

    db_session.add_all(
        [
            open_task,
            overdue_task,
            completed_task,
        ]
    )

    compliance_case = ComplianceCase(
        customer_id=customer_2.id,
        case_type=ComplianceCaseType.CUSTOMER_REVIEW,
        priority=ComplianceCasePriority.HIGH,
        status=ComplianceCaseStatus.OPEN,
        assigned_to=reviewer.id,
    )

    closed_case = ComplianceCase(
        customer_id=customer_3.id,
        case_type=ComplianceCaseType.CUSTOMER_REVIEW,
        priority=ComplianceCasePriority.LOW,
        status=ComplianceCaseStatus.CLOSED,
    )

    db_session.add_all(
        [
            compliance_case,
            closed_case,
        ]
    )

    db_session.commit()

    response = client.get(
        "/api/v1/dashboard/operations",
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True

    data = body["data"]

    assert data["customers"]["total_customers"] == 4
    assert data["customers"]["new_registrations"] == 4
    assert data["customers"]["pending_verification"] == 1
    assert data["customers"]["verified_customers"] == 2

    assert data["workflows"]["active_workflows"] == 1
    assert data["workflows"]["completed_workflows"] == 1
    assert data["workflows"]["failed_workflows"] == 1

    assert data["tasks"]["open_tasks"] == 2
    assert data["tasks"]["completed_tasks"] == 1
    assert data["tasks"]["overdue_tasks"] == 1

    assert data["compliance"]["open_cases"] == 1
    assert data["compliance"]["high_risk_customers"] == 1
    assert data["compliance"]["pending_reviews"] == 1


def test_operations_dashboard_filters_by_country(
    client,
    db_session,
    create_test_user,
    create_test_customer,
    cleanup_test_customers,
    cleanup_workflows,
    cleanup_workflow_executions,
    cleanup_tasks,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "dashboard-country-admin@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    sudan_customer = create_test_customer(
        country_of_residence="Sudan",
        status=CustomerStatus.NEW,
    )

    uk_customer = create_test_customer(
        country_of_residence="United Kingdom",
        status=CustomerStatus.NEW,
    )

    workflow = Workflow(
        name="Dashboard Country Workflow",
        status=WorkflowStatus.ACTIVE,
    )

    db_session.add(workflow)
    db_session.flush()

    sudan_execution = WorkflowExecution(
        workflow_id=workflow.id,
        entity_type="customer",
        entity_id=sudan_customer.id,
        status=WorkflowExecutionStatus.IN_PROGRESS,
        started_by=admin.id,
    )

    uk_execution = WorkflowExecution(
        workflow_id=workflow.id,
        entity_type="customer",
        entity_id=uk_customer.id,
        status=WorkflowExecutionStatus.IN_PROGRESS,
        started_by=admin.id,
    )

    db_session.add_all(
        [
            sudan_execution,
            uk_execution,
        ]
    )

    db_session.flush()

    db_session.add(
        Task(
            title="Sudan task",
            status=TaskStatus.IN_PROGRESS,
            assigned_to=admin.id,
            workflow_execution_id=sudan_execution.id,
        )
    )

    db_session.add(
        Task(
            title="UK task",
            status=TaskStatus.IN_PROGRESS,
            assigned_to=admin.id,
            workflow_execution_id=uk_execution.id,
        )
    )

    db_session.commit()

    response = client.get(
        "/api/v1/dashboard/operations?country=Sudan",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["customers"]["total_customers"] == 1
    assert data["workflows"]["active_workflows"] == 1
    assert data["tasks"]["open_tasks"] == 1


def test_operations_dashboard_filters_by_user_role(
    client,
    db_session,
    create_test_user,
    cleanup_tasks,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "dashboard-role-admin@example.com",
    )

    reviewer = create_test_user(
        UserRole.REVIEWER,
        "dashboard-role-reviewer@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    db_session.add(
        Task(
            title="Reviewer task",
            status=TaskStatus.IN_PROGRESS,
            assigned_to=reviewer.id,
        )
    )

    db_session.add(
        Task(
            title="Admin task",
            status=TaskStatus.IN_PROGRESS,
            assigned_to=admin.id,
        )
    )

    db_session.commit()

    response = client.get(
        "/api/v1/dashboard/operations",
        params={
            "user_role": UserRole.REVIEWER.value,
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["tasks"]["open_tasks"] == 1
    assert data["filters"]["user_role"] == UserRole.REVIEWER.value


def test_reviewer_cannot_access_operations_dashboard(
    client,
    create_test_user,
):
    reviewer = create_test_user(
        UserRole.REVIEWER,
        "dashboard-forbidden-reviewer@example.com",
    )

    authenticate_client(
        client,
        reviewer,
    )

    response = client.get(
        "/api/v1/dashboard/operations",
    )

    assert response.status_code == 403


def test_operations_dashboard_filters_by_date(
    client,
    db_session,
    create_test_user,
    create_test_customer,
    cleanup_test_customers,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "dashboard-date-admin@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    old_customer = create_test_customer(
        country_of_residence="Sudan",
        status=CustomerStatus.NEW,
    )

    recent_customer = create_test_customer(
        country_of_residence="Sudan",
        status=CustomerStatus.NEW,
    )

    db_session.query(type(old_customer)).filter(
        type(old_customer).id == old_customer.id
    ).update(
        {
            "created_at": datetime(
                2026,
                9,
                1,
                tzinfo=timezone.utc,
            )
        }
    )

    db_session.query(type(recent_customer)).filter(
        type(recent_customer).id == recent_customer.id
    ).update(
        {
            "created_at": datetime(
                2026,
                10,
                2,
                tzinfo=timezone.utc,
            )
        }
    )

    db_session.commit()

    response = client.get(
        "/api/v1/dashboard/operations",
        params={
            "start_date": "2026-10-01",
            "end_date": "2026-10-03",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["customers"]["total_customers"] == 1
    assert data["customers"]["new_registrations"] == 1


def test_operations_dashboard_rejects_invalid_date_range(
    client,
    create_test_user,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "dashboard-invalid-date@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.get(
        "/api/v1/dashboard/operations",
        params={
            "start_date": "2026-10-10",
            "end_date": "2026-10-01",
        },
    )

    assert response.status_code == 400
