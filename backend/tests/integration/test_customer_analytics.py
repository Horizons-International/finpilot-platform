from datetime import datetime, timezone

from app.models.verification_case import IdentityVerificationCase
from app.models.workflow import Workflow, WorkflowExecution
from app.utils.enums import (
    CustomerStatus,
    UserRole,
    VerificationStatus,
    VerificationType,
    WorkflowExecutionStatus,
)
from tests.helpers import authenticate_client


def test_customer_analytics_returns_accurate_metrics(
    client,
    db_session,
    create_test_user,
    create_test_customer,
    cleanup_test_customers,
    cleanup_workflows,
    cleanup_workflow_executions,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "customer-analytics-admin@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    customer_1 = create_test_customer(
        country_of_residence="Sudan",
        status=CustomerStatus.VERIFIED,
        created_at=datetime(
            2030,
            1,
            1,
            8,
            0,
            tzinfo=timezone.utc,
        ),
    )

    customer_2 = create_test_customer(
        country_of_residence="Sudan",
        status=CustomerStatus.PENDING_VERIFICATION,
        created_at=datetime(
            2030,
            1,
            2,
            8,
            0,
            tzinfo=timezone.utc,
        ),
    )

    customer_3 = create_test_customer(  # noqa: F841
        country_of_residence="Sudan",
        status=CustomerStatus.SUSPENDED,
        created_at=datetime(
            2030,
            1,
            2,
            10,
            0,
            tzinfo=timezone.utc,
        ),
    )

    verification_1 = IdentityVerificationCase(
        customer_id=customer_1.id,
        verification_type=VerificationType.IDENTITY,
        status=VerificationStatus.APPROVED,
        created_at=datetime(
            2030,
            1,
            1,
            9,
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

    verification_2 = IdentityVerificationCase(
        customer_id=customer_2.id,
        verification_type=VerificationType.IDENTITY,
        status=VerificationStatus.REJECTED,
        created_at=datetime(
            2030,
            1,
            2,
            9,
            0,
            tzinfo=timezone.utc,
        ),
        completed_at=datetime(
            2030,
            1,
            2,
            13,
            0,
            tzinfo=timezone.utc,
        ),
    )

    db_session.add_all(
        [
            verification_1,
            verification_2,
        ]
    )

    workflow = (
        db_session.query(Workflow)
        .filter(
            Workflow.name == "Customer Onboarding",
        )
        .first()
    )

    assert workflow is not None

    onboarding_execution = WorkflowExecution(
        workflow_id=workflow.id,
        entity_type="customer",
        entity_id=customer_1.id,
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

    db_session.add(onboarding_execution)
    db_session.commit()

    response = client.get(
        "/api/v1/analytics/customer-summary",
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

    assert data["overview"]["total_customers"] == 3
    assert data["overview"]["new_customers_during_period"] == 3

    assert data["overview"]["active_customers"] == 2
    assert data["overview"]["inactive_customers"] == 1

    assert data["overview"]["customers_by_country"][0]["customer_count"] >= 2

    verification_statuses = {
        row["status"]: row["customer_count"]
        for row in data["overview"]["customers_by_verification_status"]
    }

    assert verification_statuses["APPROVED"] == 1
    assert verification_statuses["REJECTED"] == 1
    assert verification_statuses["NO_VERIFICATION_CASE"] == 1

    lifecycle = data["lifecycle"]

    assert lifecycle["average_onboarding_completion_time_hours"] == 4.0

    assert lifecycle["verification_completion_rate_percentage"] == 100.0

    assert lifecycle["verification_rejection_rate_percentage"] == 50.0

    assert lifecycle["pending_verification_count"] == 1


def test_customer_analytics_filters_by_country(
    client,
    create_test_user,
    create_test_customer,
    cleanup_test_customers,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "customer-analytics-country-admin@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    create_test_customer(
        country_of_residence="Sudan",
        status=CustomerStatus.VERIFIED,
    )

    create_test_customer(
        country_of_residence="United Kingdom",
        status=CustomerStatus.VERIFIED,
    )

    response = client.get(
        "/api/v1/analytics/customer-summary",
        params={
            "country": "Sudan",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["filters"]["country"] == "Sudan"
    assert data["overview"]["customers_by_country"][0]["country"] == "Sudan"


def test_customer_analytics_filters_by_customer_status(
    client,
    create_test_user,
    create_test_customer,
    cleanup_test_customers,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "customer-analytics-status-admin@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    create_test_customer(
        country_of_residence="Sudan",
        status=CustomerStatus.VERIFIED,
    )

    create_test_customer(
        country_of_residence="Sudan",
        status=CustomerStatus.SUSPENDED,
    )

    response = client.get(
        "/api/v1/analytics/customer-summary",
        params={
            "status": CustomerStatus.SUSPENDED.value,
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["filters"]["status"] == CustomerStatus.SUSPENDED.value

    assert data["overview"]["total_customers"] >= 1
    assert data["overview"]["active_customers"] == 0
    assert data["overview"]["inactive_customers"] >= 1


def test_customer_analytics_rejects_invalid_date_range(
    client,
    create_test_user,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "customer-analytics-invalid-date@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.get(
        "/api/v1/analytics/customer-summary",
        params={
            "start_date": "2030-03-10",
            "end_date": "2030-03-01",
        },
    )

    assert response.status_code == 400


def test_customer_analytics_rejects_range_longer_than_366_days(
    client,
    create_test_user,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "customer-analytics-long-range@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.get(
        "/api/v1/analytics/customer-summary",
        params={
            "start_date": "2028-01-01",
            "end_date": "2030-01-01",
        },
    )

    assert response.status_code == 400


def test_reviewer_cannot_access_customer_analytics(
    client,
    create_test_user,
):
    reviewer = create_test_user(
        UserRole.REVIEWER,
        "customer-analytics-forbidden-reviewer@example.com",
    )

    authenticate_client(
        client,
        reviewer,
    )

    response = client.get(
        "/api/v1/analytics/customer-summary",
    )

    assert response.status_code == 403


def test_auditor_can_access_customer_analytics(
    client,
    create_test_user,
):
    auditor = create_test_user(
        UserRole.AUDITOR,
        "customer-analytics-auditor@example.com",
    )

    authenticate_client(
        client,
        auditor,
    )

    response = client.get(
        "/api/v1/analytics/customer-summary",
    )

    assert response.status_code == 200


def test_customer_analytics_uses_default_date_range(
    client,
    create_test_user,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "customer-analytics-default-range@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.get(
        "/api/v1/analytics/customer-summary",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["filters"]["start_date"] is not None
    assert data["filters"]["end_date"] is not None
    assert data["filters"]["start_date"] <= data["filters"]["end_date"]
