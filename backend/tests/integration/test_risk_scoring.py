from uuid import UUID

import pytest

from app.models.audit_log import AuditLog
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.risk_scoring_rule import RiskScoringRule
from app.utils.enums import (
    AuditEventType,
    CustomerRiskLevel,
    RiskRuleOperator,
    UserRole,
)
from tests.helpers import (
    authenticate_client,
    create_customer_with_data,
)


@pytest.fixture
def configured_risk_rules(db_session):
    rules = [
        RiskScoringRule(
            factor_key="country",
            operator=RiskRuleOperator.EQUALS,
            expected_value="HIGH_RISK",
            score_points=40,
            description="High-risk country.",
            priority=10,
            is_active=True,
        ),
        RiskScoringRule(
            factor_key="verification_status",
            operator=RiskRuleOperator.EQUALS,
            expected_value="PENDING",
            score_points=30,
            description="Pending verification.",
            priority=20,
            is_active=True,
        ),
        RiskScoringRule(
            factor_key="previous_compliance_cases",
            operator=RiskRuleOperator.GREATER_THAN_OR_EQUAL,
            expected_value=2,
            score_points=20,
            description="Previous compliance cases.",
            priority=30,
            is_active=True,
        ),
    ]

    db_session.add_all(rules)
    db_session.commit()

    return rules


def test_customer_risk_score_is_calculated(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_risk_scoring_configuration,
    configured_risk_thresholds,
    configured_risk_rules,
):
    admin = create_test_user(
        email="risk-score-calculation@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="risk-score-calculation-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = client.post(
        f"/api/v1/customers/{customer_id}/risk-score",
        json={
            "factors": {
                "country": "HIGH_RISK",
                "verification_status": "PENDING",
                "previous_compliance_cases": 2,
            },
            "risk_category": "AUTOMATED",
            "assessment_source": "RISK_SCORING_ENGINE",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["customer_id"] == customer_id
    assert data["risk_score"] == 90
    assert data["risk_level"] == "HIGH"
    assert data["risk_category"] == "AUTOMATED"
    assert data["assessment_source"] == "RISK_SCORING_ENGINE"


def test_low_risk_score_is_assigned_low(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_risk_scoring_configuration,
    configured_risk_thresholds,
    db_session,
):
    db_session.add(
        RiskScoringRule(
            factor_key="country",
            operator=RiskRuleOperator.EQUALS,
            expected_value="LOW_RISK",
            score_points=20,
            description="Low-risk country.",
            priority=10,
            is_active=True,
        )
    )
    db_session.commit()

    admin = create_test_user(
        email="risk-score-low@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="risk-score-low-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = client.post(
        f"/api/v1/customers/{customer_id}/risk-score",
        json={
            "factors": {
                "country": "LOW_RISK",
            },
            "risk_category": "AUTOMATED",
            "assessment_source": "RISK_SCORING_ENGINE",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["risk_score"] == 20
    assert data["risk_level"] == "LOW"


def test_medium_risk_score_is_assigned_medium(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_risk_scoring_configuration,
    configured_risk_thresholds,
    db_session,
):
    db_session.add_all(
        [
            RiskScoringRule(
                factor_key="country",
                operator=RiskRuleOperator.EQUALS,
                expected_value="MEDIUM_RISK",
                score_points=30,
                description="Medium-risk country.",
                priority=10,
                is_active=True,
            ),
            RiskScoringRule(
                factor_key="verification_status",
                operator=RiskRuleOperator.EQUALS,
                expected_value="PENDING",
                score_points=30,
                description="Pending verification.",
                priority=20,
                is_active=True,
            ),
        ]
    )
    db_session.commit()

    admin = create_test_user(
        email="risk-score-medium@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="risk-score-medium-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = client.post(
        f"/api/v1/customers/{customer_id}/risk-score",
        json={
            "factors": {
                "country": "MEDIUM_RISK",
                "verification_status": "PENDING",
            },
            "risk_category": "AUTOMATED",
            "assessment_source": "RISK_SCORING_ENGINE",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["risk_score"] == 60
    assert data["risk_level"] == "MEDIUM"


def test_high_risk_score_is_assigned_high(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_risk_scoring_configuration,
    configured_risk_thresholds,
    configured_risk_rules,
):
    admin = create_test_user(
        email="risk-score-high@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="risk-score-high-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = client.post(
        f"/api/v1/customers/{customer_id}/risk-score",
        json={
            "factors": {
                "country": "HIGH_RISK",
                "verification_status": "PENDING",
            },
            "risk_category": "AUTOMATED",
            "assessment_source": "RISK_SCORING_ENGINE",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["risk_score"] == 70
    assert data["risk_level"] == "MEDIUM"


def test_non_matching_rules_do_not_add_score(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_risk_scoring_configuration,
    configured_risk_thresholds,
    configured_risk_rules,
):
    admin = create_test_user(
        email="risk-score-no-match@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="risk-score-no-match-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = client.post(
        f"/api/v1/customers/{customer_id}/risk-score",
        json={
            "factors": {
                "country": "LOW_RISK",
                "verification_status": "APPROVED",
                "previous_compliance_cases": 0,
            },
            "risk_category": "AUTOMATED",
            "assessment_source": "RISK_SCORING_ENGINE",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["risk_score"] == 0
    assert data["risk_level"] == "LOW"


def test_calculation_result_is_stored_in_customer_risk_profile(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_risk_scoring_configuration,
    configured_risk_thresholds,
    configured_risk_rules,
    db_session,
):
    admin = create_test_user(
        email="risk-score-storage@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="risk-score-storage-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = client.post(
        f"/api/v1/customers/{customer_id}/risk-score",
        json={
            "factors": {
                "country": "HIGH_RISK",
                "verification_status": "PENDING",
                "previous_compliance_cases": 2,
            },
            "risk_category": "AUTOMATED",
            "assessment_source": "RISK_SCORING_ENGINE",
        },
    )

    assert response.status_code == 200

    profile = (
        db_session.query(CustomerRiskProfile)
        .filter(CustomerRiskProfile.customer_id == UUID(customer_id))
        .first()
    )

    assert profile is not None
    assert profile.risk_score == 90
    assert profile.risk_level == CustomerRiskLevel.HIGH
    assert profile.risk_category == "AUTOMATED"
    assert profile.assessment_source == "RISK_SCORING_ENGINE"


def test_calculation_details_contain_applied_rules(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_risk_scoring_configuration,
    configured_risk_thresholds,
    configured_risk_rules,
    db_session,
):
    admin = create_test_user(
        email="risk-score-details@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="risk-score-details-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    factors = {
        "country": "HIGH_RISK",
        "verification_status": "PENDING",
        "previous_compliance_cases": 2,
    }

    response = client.post(
        f"/api/v1/customers/{customer_id}/risk-score",
        json={
            "factors": factors,
            "risk_category": "AUTOMATED",
            "assessment_source": "RISK_SCORING_ENGINE",
        },
    )

    assert response.status_code == 200

    profile = (
        db_session.query(CustomerRiskProfile)
        .filter(CustomerRiskProfile.customer_id == UUID(customer_id))
        .first()
    )

    assert profile is not None

    details = profile.calculation_details

    assert details is not None
    assert details["factors"] == factors
    assert len(details["applied_rules"]) == 3

    applied_factor_keys = {item["factor_key"] for item in details["applied_rules"]}

    assert applied_factor_keys == {
        "country",
        "verification_status",
        "previous_compliance_cases",
    }


def test_recalculating_customer_risk_score_updates_existing_profile(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_risk_scoring_configuration,
    configured_risk_thresholds,
    configured_risk_rules,
    db_session,
):
    admin = create_test_user(
        email="risk-score-recalculate@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="risk-score-recalculate-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    first_response = client.post(
        f"/api/v1/customers/{customer_id}/risk-score",
        json={
            "factors": {
                "country": "HIGH_RISK",
                "verification_status": "PENDING",
                "previous_compliance_cases": 2,
            },
            "risk_category": "AUTOMATED",
            "assessment_source": "RISK_SCORING_ENGINE",
        },
    )

    assert first_response.status_code == 200

    first_profile_id = first_response.json()["data"]["id"]

    second_response = client.post(
        f"/api/v1/customers/{customer_id}/risk-score",
        json={
            "factors": {
                "country": "LOW_RISK",
                "verification_status": "APPROVED",
                "previous_compliance_cases": 0,
            },
            "risk_category": "AUTOMATED",
            "assessment_source": "RISK_SCORING_ENGINE",
        },
    )

    assert second_response.status_code == 200

    second_data = second_response.json()["data"]

    assert second_data["id"] == first_profile_id
    assert second_data["risk_score"] == 0
    assert second_data["risk_level"] == "LOW"

    profiles = (
        db_session.query(CustomerRiskProfile)
        .filter(CustomerRiskProfile.customer_id == UUID(customer_id))
        .all()
    )

    assert len(profiles) == 1


def test_nonexistent_customer_returns_404(
    client,
    create_test_user,
    cleanup_risk_scoring_configuration,
    configured_risk_thresholds,
    configured_risk_rules,
):
    admin = create_test_user(
        email="risk-score-missing-customer@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = client.post(
        "/api/v1/customers/00000000-0000-0000-0000-000000000000/risk-score",
        json={
            "factors": {
                "country": "HIGH_RISK",
            },
            "risk_category": "AUTOMATED",
            "assessment_source": "RISK_SCORING_ENGINE",
        },
    )

    assert response.status_code == 404

    data = response.json()

    assert data["success"] is False


def test_empty_factors_are_rejected(
    client,
    create_test_user,
    cleanup_test_customers,
):
    admin = create_test_user(
        email="risk-score-empty-factors@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="risk-score-empty-factors-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = client.post(
        f"/api/v1/customers/{customer_id}/risk-score",
        json={
            "factors": {},
            "risk_category": "AUTOMATED",
            "assessment_source": "RISK_SCORING_ENGINE",
        },
    )

    assert response.status_code == 422


def test_reviewer_cannot_calculate_risk_score(
    client,
    create_test_user,
    cleanup_test_customers,
):
    reviewer = create_test_user(
        email="risk-score-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    admin = create_test_user(
        email="risk-score-audit@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="risk-score-reviewer-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    authenticate_client(client, reviewer)

    response = client.post(
        f"/api/v1/customers/{customer_id}/risk-score",
        json={
            "factors": {
                "country": "HIGH_RISK",
            },
            "risk_category": "AUTOMATED",
            "assessment_source": "RISK_SCORING_ENGINE",
        },
    )

    assert response.status_code == 403


def test_auditor_cannot_calculate_risk_score(
    client,
    create_test_user,
    cleanup_test_customers,
):
    admin = create_test_user(
        email="risk-score-audit@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    auditor = create_test_user(
        email="risk-score-auditor@example.com",
        role=UserRole.AUDITOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="risk-score-auditor-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    authenticate_client(client, auditor)

    response = client.post(
        f"/api/v1/customers/{customer_id}/risk-score",
        json={
            "factors": {
                "country": "HIGH_RISK",
            },
            "risk_category": "AUTOMATED",
            "assessment_source": "RISK_SCORING_ENGINE",
        },
    )

    assert response.status_code == 403


def test_compliance_officer_can_calculate_risk_score(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_risk_scoring_configuration,
    configured_risk_thresholds,
    configured_risk_rules,
):
    compliance_officer = create_test_user(
        email="risk-score-compliance@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    admin = create_test_user(
        email="risk-score-audit@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="risk-score-compliance-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    authenticate_client(client, compliance_officer)

    response = client.post(
        f"/api/v1/customers/{customer_id}/risk-score",
        json={
            "factors": {
                "country": "HIGH_RISK",
                "verification_status": "PENDING",
                "previous_compliance_cases": 2,
            },
            "risk_category": "AUTOMATED",
            "assessment_source": "RISK_SCORING_ENGINE",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["risk_score"] == 90
    assert data["risk_level"] == "HIGH"


def test_risk_score_calculation_is_audited(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_risk_scoring_configuration,
    configured_risk_thresholds,
    configured_risk_rules,
    db_session,
):
    admin = create_test_user(
        email="risk-score-audit@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="risk-score-audit-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = client.post(
        f"/api/v1/customers/{customer_id}/risk-score",
        json={
            "factors": {
                "country": "HIGH_RISK",
                "verification_status": "PENDING",
                "previous_compliance_cases": 2,
            },
            "risk_category": "AUTOMATED",
            "assessment_source": "RISK_SCORING_ENGINE",
        },
    )

    assert response.status_code == 200

    profile_id = response.json()["data"]["id"]

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == admin.id,
            AuditLog.event_type == AuditEventType.CUSTOMER_RISK_SCORE_CALCULATED,
            AuditLog.resource_type == "customer_risk_profile",
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )

    assert audit_log is not None
    assert audit_log.resource_id is not None
    assert str(audit_log.resource_id) == profile_id
