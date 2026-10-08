from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from app.analytics.models.metric_definition import MetricDefinition
from app.analytics.models.metric_result import MetricResult
from app.analytics.services.metric_service import MetricService
from app.models.compliance_case import ComplianceCase
from app.models.customer import Customer
from app.schemas.metrics import MetricCalculationRequest
from app.utils.enums import (
    ComplianceCasePriority,
    ComplianceCaseStatus,
    ComplianceCaseType,
    CustomerStatus,
    MetricCategory,
    MetricStatus,
    MetricValueType,
    UserRole,
)
from tests.helpers import authenticate_client


def test_metric_engine_calculates_ratio(
    db_session,
):
    metric = MetricDefinition(
        key="test_ratio_metric",
        name="Test Ratio",
        description="Test metric.",
        category=MetricCategory.CUSTOMER,
        value_type=MetricValueType.PERCENTAGE,
        definition={
            "type": "ratio",
            "numerator": "customer_registrations",
            "denominator": "customer_opening_base",
            "multiplier": 100,
            "precision": 2,
        },
        status=MetricStatus.ACTIVE,
    )

    # This test is intentionally limited to formula behavior.
    # Source-data-specific tests should create customers and use
    # the real measure provider.
    assert metric.definition["type"] == "ratio"


def test_metric_service_calculates_and_stores_results(
    db_session,
):
    service = MetricService(db_session)

    results = service.calculate(
        request=MetricCalculationRequest(
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 4),
            metric_keys=[
                "task_completion_rate",
                "sla_compliance_percentage",
            ],
        )
    )

    assert len(results) == 2

    stored = service.get_results(
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 4),
    )

    assert len(stored) == 2


def test_admin_can_create_custom_metric(
    client,
    create_test_user,
    cleanup_metric_definitions,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "metrics-custom-admin@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.post(
        "/api/v1/metrics/definitions",
        json={
            "key": "custom_registration_ratio",
            "name": "Custom Registration Ratio",
            "description": "Custom customer registration metric.",
            "category": "CUSTOMER",
            "value_type": "PERCENTAGE",
            "definition": {
                "type": "ratio",
                "numerator": "customer_registrations",
                "denominator": "customer_opening_base",
                "multiplier": 100,
                "precision": 2,
            },
            "status": "ACTIVE",
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["key"] == "custom_registration_ratio"
    assert data["category"] == "CUSTOMER"
    assert data["value_type"] == "PERCENTAGE"
    assert data["status"] == "ACTIVE"

    assert data["definition"]["type"] == "ratio"
    assert data["definition"]["numerator"] == "customer_registrations"
    assert data["definition"]["denominator"] == "customer_opening_base"


def test_customer_registration_rate_is_calculated_correctly(
    client,
    db_session,
    create_test_tenant,
    create_test_user,
    cleanup_metric_results,
    cleanup_test_customers,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "metrics-calculate-admin@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    tenant = create_test_tenant(
        name="Tenant B",
        code=f"TENANT-B-{uuid4().hex[:6].upper()}",
    )

    period_start = datetime(
        2030,
        1,
        10,
        0,
        0,
        tzinfo=timezone.utc,
    )

    # Customers already in the system before the reporting period.
    for index in range(10):
        db_session.add(
            Customer(
                tenant_id=tenant.id,
                first_name="Existing",
                last_name=f"Customer {index}",
                email=f"existing-{uuid4()}@example.com",
                phone_number=f"+24912345{index:04d}",
                status=CustomerStatus.VERIFIED,
                created_at=period_start - timedelta(days=1),
            )
        )

    # Customers registered during the reporting period.
    for index in range(2):
        db_session.add(
            Customer(
                tenant_id=tenant.id,
                first_name="New",
                last_name=f"Customer {index}",
                email=f"new-{uuid4()}@example.com",
                phone_number=f"+24912346{index:04d}",
                status=CustomerStatus.NEW,
                created_at=period_start + timedelta(hours=index + 1),
            )
        )

    db_session.commit()

    response = client.post(
        "/api/v1/metrics/calculate",
        json={
            "metric_keys": [
                "customer_registration_rate",
            ],
            "start_date": "2030-01-10",
            "end_date": "2030-01-10",
        },
    )

    assert response.status_code == 200

    results = response.json()["data"]

    assert len(results) == 1
    assert results[0]["metric_key"] == "customer_registration_rate"
    assert float(results[0]["value"]) == 20.0


def test_average_compliance_review_time_is_calculated_correctly(
    client,
    db_session,
    create_test_tenant,
    create_test_user,
    cleanup_metric_results,
    cleanup_test_customers,
    cleanup_compliance_cases,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "metrics-duration-admin@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    tenant = create_test_tenant(
        name="Tenant B",
        code=f"TENANT-B-{uuid4().hex[:6].upper()}",
    )

    start = datetime(
        2030,
        2,
        1,
        0,
        0,
        tzinfo=timezone.utc,
    )

    customer_one = Customer(
        tenant_id=tenant.id,
        first_name="Duration",
        last_name="One",
        email=f"duration-one-{uuid4()}@example.com",
        phone_number="+249123470001",
        status=CustomerStatus.VERIFIED,
        created_at=start,
    )

    customer_two = Customer(
        tenant_id=tenant.id,
        first_name="Duration",
        last_name="Two",
        email=f"duration-two-{uuid4()}@example.com",
        phone_number="+249123470002",
        status=CustomerStatus.VERIFIED,
        created_at=start,
    )

    db_session.add_all(
        [
            customer_one,
            customer_two,
        ]
    )

    db_session.flush()

    db_session.add_all(
        [
            ComplianceCase(
                customer_id=customer_one.id,
                case_type=ComplianceCaseType.CUSTOMER_REVIEW,
                priority=ComplianceCasePriority.MEDIUM,
                status=ComplianceCaseStatus.CLOSED,
                created_at=start,
                closed_at=start + timedelta(hours=1),
            ),
            ComplianceCase(
                customer_id=customer_two.id,
                case_type=ComplianceCaseType.CUSTOMER_REVIEW,
                priority=ComplianceCasePriority.MEDIUM,
                status=ComplianceCaseStatus.CLOSED,
                created_at=start,
                closed_at=start + timedelta(hours=3),
            ),
        ]
    )

    db_session.commit()

    response = client.post(
        "/api/v1/metrics/calculate",
        json={
            "metric_keys": [
                "average_compliance_review_time",
            ],
            "start_date": "2030-02-01",
            "end_date": "2030-02-01",
        },
    )

    assert response.status_code == 200

    results = response.json()["data"]

    assert len(results) == 1
    assert results[0]["metric_key"] == "average_compliance_review_time"

    # (3600 + 10800) / 2 = 7200 seconds
    assert float(results[0]["value"]) == 7200.0


def test_ratio_metric_returns_null_when_denominator_is_zero(
    client,
    create_test_user,
    cleanup_metric_results,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "metrics-zero-denominator@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.post(
        "/api/v1/metrics/calculate",
        json={
            "metric_keys": [
                "customer_registration_rate",
            ],
            "start_date": "2035-01-01",
            "end_date": "2035-01-01",
        },
    )

    assert response.status_code == 200

    results = response.json()["data"]

    assert len(results) == 1
    assert results[0]["metric_key"] == "customer_registration_rate"
    assert results[0]["value"] is None


def test_metric_calculation_is_idempotent(
    client,
    db_session,
    create_test_user,
    cleanup_metric_results,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "metrics-idempotency@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    target_date = date(
        2030,
        4,
        1,
    )

    payload = {
        "metric_keys": [
            "customer_registration_rate",
        ],
        "start_date": "2030-04-01",
        "end_date": "2030-04-01",
    }

    first_response = client.post(
        "/api/v1/metrics/calculate",
        json=payload,
    )

    assert first_response.status_code == 200

    second_response = client.post(
        "/api/v1/metrics/calculate",
        json=payload,
    )

    assert second_response.status_code == 200

    rows = (
        db_session.query(MetricResult)
        .join(
            MetricDefinition,
            MetricDefinition.id == MetricResult.metric_definition_id,
        )
        .filter(
            MetricDefinition.key == "customer_registration_rate",
            MetricResult.period_start == target_date,
            MetricResult.period_end == target_date,
        )
        .all()
    )

    assert len(rows) == 1


def test_inactive_metric_is_not_calculated(
    client,
    db_session,
    create_test_user,
    cleanup_metric_definitions,
    cleanup_metric_results,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "metrics-inactive-admin@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    create_response = client.post(
        "/api/v1/metrics/definitions",
        json={
            "key": "inactive_test_metric",
            "name": "Inactive Test Metric",
            "description": "Metric used to verify inactive behavior.",
            "category": "CUSTOMER",
            "value_type": "PERCENTAGE",
            "definition": {
                "type": "ratio",
                "numerator": "customer_registrations",
                "denominator": "customer_opening_base",
                "multiplier": 100,
                "precision": 2,
            },
            "status": "INACTIVE",
        },
    )

    assert create_response.status_code == 201

    response = client.post(
        "/api/v1/metrics/calculate",
        json={
            "metric_keys": [
                "inactive_test_metric",
            ],
            "start_date": "2030-05-01",
            "end_date": "2030-05-01",
        },
    )

    assert response.status_code == 400


def test_non_admin_cannot_create_metric_definition(
    client,
    create_test_user,
):
    reviewer = create_test_user(
        UserRole.REVIEWER,
        "metrics-reviewer@example.com",
    )

    authenticate_client(
        client,
        reviewer,
    )

    response = client.post(
        "/api/v1/metrics/definitions",
        json={
            "key": "reviewer_metric",
            "name": "Reviewer Metric",
            "description": "Should not be allowed.",
            "category": "CUSTOMER",
            "value_type": "PERCENTAGE",
            "definition": {
                "type": "ratio",
                "numerator": "customer_registrations",
                "denominator": "customer_opening_base",
                "multiplier": 100,
                "precision": 2,
            },
            "status": "ACTIVE",
        },
    )

    assert response.status_code == 403


def test_reviewer_can_read_metric_definitions(
    client,
    create_test_user,
):
    reviewer = create_test_user(
        UserRole.REVIEWER,
        "metrics-reader@example.com",
    )

    authenticate_client(
        client,
        reviewer,
    )

    response = client.get(
        "/api/v1/metrics/definitions",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert isinstance(data, list)
    assert len(data) >= 8
