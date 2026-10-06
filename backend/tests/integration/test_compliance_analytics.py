from datetime import date, datetime, timedelta, timezone

from app.analytics.models.compliance_daily import ComplianceAnalyticsDaily
from app.models.compliance_case import ComplianceCase
from app.models.verification_case import IdentityVerificationCase
from app.models.verification_review import VerificationReview
from app.utils.enums import (
    ComplianceCasePriority,
    ComplianceCaseStatus,
    ComplianceCaseType,
    ReviewDecision,
    UserRole,
    VerificationStatus,
    VerificationType,
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


def test_compliance_analytics_returns_metrics_and_trends(
    client,
    db_session,
    create_test_user,
    create_test_customer,
    cleanup_test_customers,
    cleanup_compliance_cases,
    cleanup_analytics_snapshots,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "compliance-analytics-admin@example.com",
    )

    reviewer = create_test_user(
        UserRole.REVIEWER,
        "compliance-analytics-reviewer@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    db_session.add_all(
        [
            ComplianceAnalyticsDaily(
                snapshot_date=date(2030, 1, 1),
                ending_total_cases=10,
                cases_created_during_day=3,
                ending_open_cases=7,
                ending_resolved_cases=2,
                ending_closed_cases=1,
                ending_total_alerts=5,
                alerts_created_during_day=2,
                ending_low_severity_alerts=2,
                ending_medium_severity_alerts=1,
                ending_high_severity_alerts=1,
                ending_critical_severity_alerts=1,
                ending_low_risk_customers=80,
                ending_medium_risk_customers=30,
                ending_high_risk_customers=10,
                ending_critical_risk_customers=2,
            ),
            ComplianceAnalyticsDaily(
                snapshot_date=date(2030, 1, 2),
                ending_total_cases=14,
                cases_created_during_day=4,
                ending_open_cases=8,
                ending_resolved_cases=3,
                ending_closed_cases=3,
                ending_total_alerts=8,
                alerts_created_during_day=3,
                ending_low_severity_alerts=3,
                ending_medium_severity_alerts=2,
                ending_high_severity_alerts=2,
                ending_critical_severity_alerts=1,
                ending_low_risk_customers=85,
                ending_medium_risk_customers=32,
                ending_high_risk_customers=12,
                ending_critical_risk_customers=3,
            ),
        ]
    )

    customer = create_test_customer()

    created_at_1 = datetime(
        2030,
        1,
        1,
        9,
        0,
        tzinfo=timezone.utc,
    )

    created_at_2 = datetime(
        2030,
        1,
        2,
        10,
        0,
        tzinfo=timezone.utc,
    )

    db_session.add_all(
        [
            ComplianceCase(
                customer_id=customer.id,
                case_type=ComplianceCaseType.CUSTOMER_REVIEW,
                priority=ComplianceCasePriority.MEDIUM,
                status=ComplianceCaseStatus.CLOSED,
                created_at=created_at_1,
                closed_at=created_at_1 + timedelta(hours=4),
                assigned_to=reviewer.id,
            ),
            ComplianceCase(
                customer_id=customer.id,
                case_type=ComplianceCaseType.AML_ALERT,
                priority=ComplianceCasePriority.HIGH,
                status=ComplianceCaseStatus.CLOSED,
                created_at=created_at_2,
                closed_at=created_at_2 + timedelta(hours=2),
                assigned_to=reviewer.id,
            ),
        ]
    )

    verification_case = IdentityVerificationCase(
        customer_id=customer.id,
        verification_type=VerificationType.IDENTITY,
        status=VerificationStatus.REJECTED,
        assigned_to=reviewer.id,
        created_at=created_at_2,
        completed_at=created_at_2 + timedelta(hours=1),
    )

    db_session.add(verification_case)
    db_session.flush()

    db_session.add_all(
        [
            VerificationReview(
                verification_case_id=verification_case.id,
                reviewer_id=reviewer.id,
                decision=ReviewDecision.REJECT,
                notes="Invalid identity document",
                created_at=created_at_2,
            ),
            VerificationReview(
                verification_case_id=verification_case.id,
                reviewer_id=reviewer.id,
                decision=ReviewDecision.REJECT,
                notes="Invalid identity document",
                created_at=created_at_2,
            ),
            VerificationReview(
                verification_case_id=verification_case.id,
                reviewer_id=reviewer.id,
                decision=ReviewDecision.REJECT,
                notes=None,
                created_at=created_at_2,
            ),
        ]
    )

    db_session.commit()

    response = client.get(
        "/api/v1/analytics/compliance",
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

    assert data["risk_distribution"]["ending_high_risk_customers"] == 12

    assert len(data["risk_distribution"]["trend"]) == 2

    assert data["aml_alert_trends"]["total_alerts_created_during_period"] == 5

    assert data["aml_alert_trends"]["ending_total_alerts"] == 8

    assert data["case_resolution_performance"]["total_cases_created_during_period"] == 2

    assert data["case_resolution_performance"]["total_cases_closed_during_period"] == 2

    assert data["case_resolution_performance"]["average_resolution_time_hours"] == 3.0

    rejection_reasons = data["verification_rejection_reasons"]

    assert rejection_reasons["total_rejections"] == 3

    assert rejection_reasons["rejection_reasons"][0] == {
        "reason": "Invalid identity document",
        "count": 2,
    }

    assert rejection_reasons["rejection_reasons"][1] == {
        "reason": "Unspecified",
        "count": 1,
    }


def test_compliance_analytics_filters_by_date(
    client,
    db_session,
    create_test_user,
    cleanup_analytics_snapshots,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "compliance-analytics-date-admin@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    db_session.add_all(
        [
            ComplianceAnalyticsDaily(
                snapshot_date=date(2030, 2, 1),
                ending_total_cases=5,
                cases_created_during_day=1,
                ending_open_cases=4,
                ending_resolved_cases=0,
                ending_closed_cases=1,
                ending_total_alerts=2,
                alerts_created_during_day=1,
                ending_low_severity_alerts=1,
                ending_medium_severity_alerts=1,
                ending_high_severity_alerts=0,
                ending_critical_severity_alerts=0,
                ending_low_risk_customers=20,
                ending_medium_risk_customers=10,
                ending_high_risk_customers=2,
                ending_critical_risk_customers=1,
            ),
            ComplianceAnalyticsDaily(
                snapshot_date=date(2030, 2, 2),
                ending_total_cases=9,
                cases_created_during_day=4,
                ending_open_cases=6,
                ending_resolved_cases=1,
                ending_closed_cases=2,
                ending_total_alerts=5,
                alerts_created_during_day=3,
                ending_low_severity_alerts=2,
                ending_medium_severity_alerts=1,
                ending_high_severity_alerts=1,
                ending_critical_severity_alerts=1,
                ending_low_risk_customers=25,
                ending_medium_risk_customers=12,
                ending_high_risk_customers=4,
                ending_critical_risk_customers=2,
            ),
        ]
    )

    db_session.commit()

    response = client.get(
        "/api/v1/analytics/compliance",
        params={
            "start_date": "2030-02-02",
            "end_date": "2030-02-02",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert len(data["risk_distribution"]["trend"]) == 1
    assert len(data["aml_alert_trends"]["trend"]) == 1

    assert data["aml_alert_trends"]["trend"][0]["alerts_created_during_day"] == 3

    assert data["risk_distribution"]["trend"][0]["ending_high_risk_customers"] == 4


def test_compliance_analytics_rejects_invalid_date_range(
    client,
    create_test_user,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "compliance-analytics-invalid-date@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.get(
        "/api/v1/analytics/compliance",
        params={
            "start_date": "2030-03-10",
            "end_date": "2030-03-01",
        },
    )

    assert response.status_code == 400


def test_reviewer_cannot_access_compliance_analytics(
    client,
    create_test_user,
):
    reviewer = create_test_user(
        UserRole.REVIEWER,
        "compliance-analytics-forbidden@example.com",
    )

    authenticate_client(
        client,
        reviewer,
    )

    response = client.get(
        "/api/v1/analytics/compliance",
    )

    assert response.status_code == 403


def test_compliance_officer_can_access_compliance_analytics(
    client,
    create_test_user,
):
    compliance_officer = create_test_user(
        UserRole.COMPLIANCE_OFFICER,
        "compliance-analytics-officer@example.com",
    )

    authenticate_client(
        client,
        compliance_officer,
    )

    response = client.get(
        "/api/v1/analytics/compliance",
    )

    assert response.status_code == 200
