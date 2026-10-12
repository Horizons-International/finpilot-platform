from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4

from app.models.aml_rule import AMLRule
from app.models.customer import Customer
from app.models.customer_risk_assessment_history import (
    CustomerRiskAssessmentHistory,
)
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.transaction_monitoring_result import (
    TransactionMonitoringResult,
)
from app.models.verification_case import IdentityVerificationCase
from app.utils.enums import (
    AMLRuleSeverity,
    AMLRuleStatus,
    AMLRuleType,
    CustomerRiskLevel,
    TransactionMonitoringOutcome,
    UserRole,
    VerificationStatus,
)
from tests.helpers import (
    authenticate_client,
    create_customer_with_data,
    create_verification_case,
)


def _customer_tenant_id(db_session, customer_id: UUID) -> UUID:

    tenant_id = cast(
        UUID | None,
        db_session.query(Customer.tenant_id)
        .filter(Customer.id == customer_id)
        .scalar(),
    )

    assert tenant_id is not None

    return tenant_id


def test_compliance_cases_report_returns_case_metrics(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
):
    manager = create_test_user(
        email=(f"reports-case-manager-{uuid4()}@example.com"),
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, manager)

    customer_response = create_customer_with_data(
        client,
        email=(f"reports-case-customer-{uuid4()}@example.com"),
        country_of_residence="SD",
    )

    assert customer_response.status_code == 201

    customer_id = UUID(customer_response.json()["data"]["id"])

    first_case = create_verification_case(
        client,
        str(customer_id),
    )

    second_case = create_verification_case(
        client,
        str(customer_id),
        verification_type="ADDRESS",
    )

    first_case_id = UUID(first_case["id"])
    second_case_id = UUID(second_case["id"])

    first = db_session.get(IdentityVerificationCase, first_case_id)
    second = db_session.get(IdentityVerificationCase, second_case_id)

    assert first is not None
    assert second is not None

    first.status = VerificationStatus.APPROVED
    first.completed_at = datetime(
        2026,
        9,
        10,
        12,
        0,
        tzinfo=timezone.utc,
    )
    first.created_at = datetime(
        2026,
        9,
        10,
        10,
        0,
        tzinfo=timezone.utc,
    )

    second.status = VerificationStatus.UNDER_REVIEW
    second.completed_at = None
    second.created_at = datetime(
        2026,
        9,
        11,
        10,
        0,
        tzinfo=timezone.utc,
    )

    db_session.commit()

    response = client.get(
        "/api/v1/reports/compliance-cases",
        params={
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
            "country": "sd",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["total_cases"] == 2
    assert data["open_cases"] == 1
    assert data["closed_cases"] == 1
    assert data["average_resolution_time_hours"] == 2.0


def test_compliance_cases_report_risk_filter_works(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
):
    manager = create_test_user(
        email=(f"reports-case-risk-manager-{uuid4()}@example.com"),
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, manager)

    customer_response = create_customer_with_data(
        client,
        email=(f"reports-case-risk-customer-{uuid4()}@example.com"),
    )

    assert customer_response.status_code == 201

    customer_id = UUID(customer_response.json()["data"]["id"])
    tenant_id = _customer_tenant_id(db_session, customer_id)

    create_verification_case(client, str(customer_id))

    profile = CustomerRiskProfile(
        tenant_id=tenant_id,
        customer_id=customer_id,
        risk_level=CustomerRiskLevel.HIGH,
        risk_score=90,
        risk_category="AML",
        assessed_at=datetime.now(timezone.utc),
        assessment_source="TEST",
        calculation_details={},
    )

    db_session.add(profile)
    db_session.commit()

    response = client.get(
        "/api/v1/reports/compliance-cases",
        params={"risk_level": "HIGH"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["total_cases"] == 1


def test_aml_alert_report_returns_matched_alerts(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
    cleanup_aml_rules,
    cleanup_transaction_monitoring_results,
):
    manager = create_test_user(
        email=(f"reports-alert-manager-{uuid4()}@example.com"),
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, manager)

    customer_response = create_customer_with_data(
        client,
        email=(f"reports-alert-customer-{uuid4()}@example.com"),
        country_of_residence="SD",
    )

    assert customer_response.status_code == 201

    customer_id = UUID(customer_response.json()["data"]["id"])
    tenant_id = _customer_tenant_id(db_session, customer_id)

    rule = AMLRule(
        tenant_id=tenant_id,
        name="Large Transaction",
        description="Report test rule",
        rule_type=AMLRuleType.TRANSACTION,
        condition={
            "field": "amount",
            "operator": ">=",
            "value": 10000,
        },
        severity=AMLRuleSeverity.HIGH,
        status=AMLRuleStatus.ACTIVE,
    )

    db_session.add(rule)
    db_session.flush()

    db_session.add(
        TransactionMonitoringResult(
            tenant_id=tenant_id,
            transaction_id=uuid4(),
            customer_id=customer_id,
            rule_id=rule.id,
            country="SD",
            result=TransactionMonitoringOutcome.MATCHED,
            created_at=datetime(
                2026,
                9,
                20,
                12,
                0,
                tzinfo=timezone.utc,
            ),
        )
    )

    db_session.add(
        TransactionMonitoringResult(
            tenant_id=tenant_id,
            transaction_id=uuid4(),
            customer_id=customer_id,
            rule_id=rule.id,
            country="SD",
            result=TransactionMonitoringOutcome.NOT_MATCHED,
            created_at=datetime(
                2026,
                9,
                20,
                13,
                0,
                tzinfo=timezone.utc,
            ),
        )
    )

    db_session.commit()

    response = client.get(
        "/api/v1/reports/aml-alerts",
        params={
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
            "country": "SD",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["total_alerts"] == 1
    assert data["alerts_by_severity"] == [{"severity": "HIGH", "count": 1}]
    assert len(data["alerts_by_rule"]) == 1
    assert data["alerts_by_rule"][0]["rule_name"] == "Large Transaction"
    assert data["alerts_by_rule"][0]["count"] == 1
    assert data["alert_status"] == [{"status": "OPEN", "count": 1}]


def test_customer_risk_report_returns_current_distribution(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
    cleanup_customer_risk_assessment_history,
):
    manager = create_test_user(
        email=(f"reports-risk-manager-{uuid4()}@example.com"),
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, manager)

    customer_response = create_customer_with_data(
        client,
        email=(f"reports-risk-customer-{uuid4()}@example.com"),
        country_of_residence="SD",
    )

    assert customer_response.status_code == 201

    customer_id = UUID(customer_response.json()["data"]["id"])
    tenant_id = _customer_tenant_id(db_session, customer_id)

    profile = CustomerRiskProfile(
        tenant_id=tenant_id,
        customer_id=customer_id,
        risk_level=CustomerRiskLevel.CRITICAL,
        risk_score=99,
        risk_category="AML",
        assessed_at=datetime(
            2026,
            9,
            25,
            12,
            0,
            tzinfo=timezone.utc,
        ),
        assessment_source="TEST",
        calculation_details={},
    )

    db_session.add(profile)

    db_session.add_all(
        [
            CustomerRiskAssessmentHistory(
                tenant_id=tenant_id,
                customer_id=customer_id,
                risk_level=CustomerRiskLevel.MEDIUM,
                risk_score=50,
                risk_category="AML",
                assessed_at=datetime(
                    2026,
                    9,
                    1,
                    12,
                    0,
                    tzinfo=timezone.utc,
                ),
                assessment_source="TEST",
            ),
            CustomerRiskAssessmentHistory(
                tenant_id=tenant_id,
                customer_id=customer_id,
                risk_level=CustomerRiskLevel.HIGH,
                risk_score=75,
                risk_category="AML",
                assessed_at=datetime(
                    2026,
                    9,
                    15,
                    12,
                    0,
                    tzinfo=timezone.utc,
                ),
                assessment_source="TEST",
            ),
            CustomerRiskAssessmentHistory(
                tenant_id=tenant_id,
                customer_id=customer_id,
                risk_level=CustomerRiskLevel.CRITICAL,
                risk_score=99,
                risk_category="AML",
                assessed_at=datetime(
                    2026,
                    9,
                    25,
                    12,
                    0,
                    tzinfo=timezone.utc,
                ),
                assessment_source="TEST",
            ),
        ]
    )

    db_session.commit()

    response = client.get(
        "/api/v1/reports/customer-risk",
        params={
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
            "country": "SD",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["high_risk_customers"] == 1

    distribution = {
        item["risk_level"]: item["count"] for item in data["customers_by_risk_level"]
    }

    assert distribution["CRITICAL"] == 1

    changes = data["risk_changes_over_time"]

    assert len(changes) == 2
    assert changes[0]["previous_risk_level"] == "MEDIUM"
    assert changes[0]["new_risk_level"] == "HIGH"
    assert changes[0]["count"] == 1
    assert changes[1]["previous_risk_level"] == "HIGH"
    assert changes[1]["new_risk_level"] == "CRITICAL"
    assert changes[1]["count"] == 1


def test_auditor_cannot_access_compliance_reports(
    client,
    create_test_user,
):
    auditor = create_test_user(
        email=(f"reports-auditor-{uuid4()}@example.com"),
        role=UserRole.AUDITOR,
    )

    authenticate_client(client, auditor)

    response = client.get("/api/v1/reports/compliance-cases")

    assert response.status_code == 403


def test_compliance_officer_can_access_compliance_reports(
    client,
    create_test_user,
):
    officer = create_test_user(
        email=(f"reports-officer-{uuid4()}@example.com"),
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(client, officer)

    response = client.get("/api/v1/reports/compliance-cases")

    assert response.status_code == 200


def test_report_rejects_invalid_date_range(
    client,
    create_test_user,
):
    manager = create_test_user(
        email=(f"reports-date-manager-{uuid4()}@example.com"),
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, manager)

    response = client.get(
        "/api/v1/reports/compliance-cases",
        params={
            "start_date": "2026-09-30",
            "end_date": "2026-09-01",
        },
    )

    assert response.status_code == 400


def test_customer_risk_report_filter_by_risk_level(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
    cleanup_customer_risk_assessment_history,
):
    manager = create_test_user(
        email=(f"reports-risk-filter-manager-{uuid4()}@example.com"),
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, manager)

    first_customer_response = create_customer_with_data(
        client,
        email=(f"reports-risk-filter-high-{uuid4()}@example.com"),
    )

    assert first_customer_response.status_code == 201

    first_customer_id = UUID(first_customer_response.json()["data"]["id"])
    first_tenant_id = _customer_tenant_id(db_session, first_customer_id)

    second_customer_response = create_customer_with_data(
        client,
        email=(f"reports-risk-filter-low-{uuid4()}@example.com"),
    )

    assert second_customer_response.status_code == 201

    second_customer_id = UUID(second_customer_response.json()["data"]["id"])
    second_tenant_id = _customer_tenant_id(db_session, second_customer_id)

    now = datetime.now(timezone.utc)

    db_session.add_all(
        [
            CustomerRiskProfile(
                tenant_id=first_tenant_id,
                customer_id=first_customer_id,
                risk_level=CustomerRiskLevel.HIGH,
                risk_score=80,
                risk_category="AML",
                assessed_at=now,
                assessment_source="TEST",
            ),
            CustomerRiskProfile(
                tenant_id=second_tenant_id,
                customer_id=second_customer_id,
                risk_level=CustomerRiskLevel.LOW,
                risk_score=10,
                risk_category="AML",
                assessed_at=now,
                assessment_source="TEST",
            ),
        ]
    )

    db_session.commit()

    response = client.get(
        "/api/v1/reports/customer-risk",
        params={"risk_level": "HIGH"},
    )

    assert response.status_code == 200

    data = response.json()["data"]

    distribution = {
        item["risk_level"]: item["count"] for item in data["customers_by_risk_level"]
    }

    assert distribution == {"HIGH": 1}
    assert data["high_risk_customers"] == 1
