from uuid import UUID

import pytest

from app.models.audit_log import AuditLog
from app.models.risk_scoring_rule import RiskScoringRule
from app.utils.enums import AuditEventType, RiskRuleOperator, UserRole
from tests.helpers import authenticate_client


@pytest.fixture
def cleanup_risk_scoring_rules(db_session):
    existing_rule_ids = {rule.id for rule in db_session.query(RiskScoringRule).all()}

    yield

    current_rules = db_session.query(RiskScoringRule).all()

    for rule in current_rules:
        if rule.id not in existing_rule_ids:
            db_session.delete(rule)

    db_session.commit()


def test_admin_can_create_risk_scoring_rule(
    client,
    create_test_user,
    cleanup_risk_scoring_rules,
):
    admin = create_test_user(
        email="risk-rule-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = client.post(
        "/api/v1/risk-scoring/rules",
        json={
            "factor_key": "country",
            "operator": "EQUALS",
            "expected_value": "SD",
            "score_points": 20,
            "description": "Risk score for configured country.",
            "priority": 10,
            "is_active": True,
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["id"] is not None
    assert data["factor_key"] == "country"
    assert data["operator"] == "EQUALS"
    assert data["expected_value"] == "SD"
    assert data["score_points"] == 20
    assert data["description"] == "Risk score for configured country."
    assert data["priority"] == 10
    assert data["is_active"] is True


def test_created_risk_scoring_rule_is_persisted(
    client,
    create_test_user,
    cleanup_risk_scoring_rules,
    db_session,
):
    admin = create_test_user(
        email="risk-rule-persist@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = client.post(
        "/api/v1/risk-scoring/rules",
        json={
            "factor_key": "verification_status",
            "operator": "EQUALS",
            "expected_value": "PENDING",
            "score_points": 30,
            "description": "Pending verification increases risk.",
            "priority": 20,
            "is_active": True,
        },
    )

    assert response.status_code == 201

    rule_id = UUID(response.json()["data"]["id"])

    rule = (
        db_session.query(RiskScoringRule).filter(RiskScoringRule.id == rule_id).first()
    )

    assert rule is not None
    assert rule.factor_key == "verification_status"
    assert rule.operator == RiskRuleOperator.EQUALS
    assert rule.expected_value == "PENDING"
    assert rule.score_points == 30
    assert rule.priority == 20
    assert rule.is_active is True


def test_admin_can_create_rule_with_list_expected_value(
    client,
    create_test_user,
    cleanup_risk_scoring_rules,
):
    admin = create_test_user(
        email="risk-rule-list@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = client.post(
        "/api/v1/risk-scoring/rules",
        json={
            "factor_key": "country",
            "operator": "IN",
            "expected_value": [
                "SD",
                "UG",
                "KE",
            ],
            "score_points": 25,
            "description": "Configured country list.",
            "priority": 10,
            "is_active": True,
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["operator"] == "IN"
    assert data["expected_value"] == [
        "SD",
        "UG",
        "KE",
    ]


def test_admin_can_create_rule_with_numeric_expected_value(
    client,
    create_test_user,
    cleanup_risk_scoring_rules,
):
    admin = create_test_user(
        email="risk-rule-number@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = client.post(
        "/api/v1/risk-scoring/rules",
        json={
            "factor_key": "previous_compliance_cases",
            "operator": "GREATER_THAN_OR_EQUAL",
            "expected_value": 3,
            "score_points": 40,
            "description": "Previous compliance cases.",
            "priority": 30,
            "is_active": True,
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["operator"] == "GREATER_THAN_OR_EQUAL"
    assert data["expected_value"] == 3


def test_admin_can_create_exists_rule(
    client,
    create_test_user,
    cleanup_risk_scoring_rules,
):
    admin = create_test_user(
        email="risk-rule-exists@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = client.post(
        "/api/v1/risk-scoring/rules",
        json={
            "factor_key": "previous_compliance_case",
            "operator": "EXISTS",
            "expected_value": None,
            "score_points": 30,
            "description": "Customer has a previous compliance case.",
            "priority": 30,
            "is_active": True,
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["operator"] == "EXISTS"
    assert data["expected_value"] is None


def test_compliance_officer_cannot_create_risk_scoring_rule(
    client,
    create_test_user,
    cleanup_risk_scoring_rules,
):
    compliance_officer = create_test_user(
        email="risk-rule-compliance@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(client, compliance_officer)

    response = client.post(
        "/api/v1/risk-scoring/rules",
        json={
            "factor_key": "country",
            "operator": "EQUALS",
            "expected_value": "SD",
            "score_points": 20,
            "description": "Should not be allowed.",
            "priority": 10,
            "is_active": True,
        },
    )

    assert response.status_code == 403

    data = response.json()

    assert data["success"] is False


def test_reviewer_cannot_create_risk_scoring_rule(
    client,
    create_test_user,
    cleanup_risk_scoring_rules,
):
    reviewer = create_test_user(
        email="risk-rule-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, reviewer)

    response = client.post(
        "/api/v1/risk-scoring/rules",
        json={
            "factor_key": "country",
            "operator": "EQUALS",
            "expected_value": "SD",
            "score_points": 20,
            "description": "Should not be allowed.",
            "priority": 10,
            "is_active": True,
        },
    )

    assert response.status_code == 403


def test_auditor_cannot_create_risk_scoring_rule(
    client,
    create_test_user,
    cleanup_risk_scoring_rules,
):
    auditor = create_test_user(
        email="risk-rule-auditor@example.com",
        role=UserRole.AUDITOR,
    )

    authenticate_client(client, auditor)

    response = client.post(
        "/api/v1/risk-scoring/rules",
        json={
            "factor_key": "country",
            "operator": "EQUALS",
            "expected_value": "SD",
            "score_points": 20,
            "description": "Should not be allowed.",
            "priority": 10,
            "is_active": True,
        },
    )

    assert response.status_code == 403


def test_admin_can_list_risk_scoring_rules(
    client,
    create_test_user,
    cleanup_risk_scoring_rules,
    db_session,
):
    admin = create_test_user(
        email="risk-rule-list-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    rule = RiskScoringRule(
        factor_key="country",
        operator=RiskRuleOperator.EQUALS,
        expected_value="SD",
        score_points=20,
        description="Test rule.",
        priority=10,
        is_active=True,
    )

    db_session.add(rule)
    db_session.commit()

    authenticate_client(client, admin)

    response = client.get(
        "/api/v1/risk-scoring/rules",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert isinstance(data, list)

    rule_ids = {item["id"] for item in data}

    assert str(rule.id) in rule_ids


def test_compliance_officer_can_list_risk_scoring_rules(
    client,
    create_test_user,
    cleanup_risk_scoring_rules,
):
    compliance_officer = create_test_user(
        email="risk-rule-list-compliance@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(client, compliance_officer)

    response = client.get(
        "/api/v1/risk-scoring/rules",
    )

    assert response.status_code == 200


def test_reviewer_cannot_list_risk_scoring_rules(
    client,
    create_test_user,
):
    reviewer = create_test_user(
        email="risk-rule-list-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, reviewer)

    response = client.get(
        "/api/v1/risk-scoring/rules",
    )

    assert response.status_code == 403


def test_auditor_cannot_list_risk_scoring_rules(
    client,
    create_test_user,
):
    auditor = create_test_user(
        email="risk-rule-list-auditor@example.com",
        role=UserRole.AUDITOR,
    )

    authenticate_client(client, auditor)

    response = client.get(
        "/api/v1/risk-scoring/rules",
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    "operator",
    [
        "EQUALS",
        "NOT_EQUALS",
        "IN",
        "NOT_IN",
        "GREATER_THAN",
        "GREATER_THAN_OR_EQUAL",
        "LESS_THAN",
        "LESS_THAN_OR_EQUAL",
        "EXISTS",
        "NOT_EXISTS",
    ],
)
def test_all_supported_rule_operators_are_accepted(
    client,
    create_test_user,
    cleanup_risk_scoring_rules,
    operator,
):
    admin = create_test_user(
        email=f"risk-rule-operator-{operator.lower()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    expected_value = None

    if operator in {"EQUALS", "NOT_EQUALS"}:
        expected_value = "SD"
    elif operator in {"IN", "NOT_IN"}:
        expected_value = ["SD", "UG"]
    elif operator in {
        "GREATER_THAN",
        "GREATER_THAN_OR_EQUAL",
        "LESS_THAN",
        "LESS_THAN_OR_EQUAL",
    }:
        expected_value = 5

    response = client.post(
        "/api/v1/risk-scoring/rules",
        json={
            "factor_key": "test_factor",
            "operator": operator,
            "expected_value": expected_value,
            "score_points": 10,
            "description": "Operator test.",
            "priority": 0,
            "is_active": True,
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["operator"] == operator


def test_invalid_operator_is_rejected(
    client,
    create_test_user,
    cleanup_risk_scoring_rules,
):
    admin = create_test_user(
        email="risk-rule-invalid-operator@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = client.post(
        "/api/v1/risk-scoring/rules",
        json={
            "factor_key": "country",
            "operator": "CONTAINS",
            "expected_value": "SD",
            "score_points": 20,
            "description": "Invalid operator.",
            "priority": 10,
            "is_active": True,
        },
    )

    assert response.status_code == 422


def test_missing_factor_key_is_rejected(
    client,
    create_test_user,
    cleanup_risk_scoring_rules,
):
    admin = create_test_user(
        email="risk-rule-missing-factor@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = client.post(
        "/api/v1/risk-scoring/rules",
        json={
            "operator": "EQUALS",
            "expected_value": "SD",
            "score_points": 20,
            "description": "Missing factor.",
            "priority": 10,
            "is_active": True,
        },
    )

    assert response.status_code == 422


def test_missing_score_points_is_rejected(
    client,
    create_test_user,
    cleanup_risk_scoring_rules,
):
    admin = create_test_user(
        email="risk-rule-missing-score@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = client.post(
        "/api/v1/risk-scoring/rules",
        json={
            "factor_key": "country",
            "operator": "EQUALS",
            "expected_value": "SD",
            "description": "Missing score.",
            "priority": 10,
            "is_active": True,
        },
    )

    assert response.status_code == 422


def test_risk_scoring_rule_creation_is_audited(
    client,
    create_test_user,
    cleanup_risk_scoring_rules,
    db_session,
):
    admin = create_test_user(
        email="risk-rule-audit@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = client.post(
        "/api/v1/risk-scoring/rules",
        json={
            "factor_key": "country",
            "operator": "EQUALS",
            "expected_value": "SD",
            "score_points": 20,
            "description": "Audit test.",
            "priority": 10,
            "is_active": True,
        },
    )

    assert response.status_code == 201

    rule_id = response.json()["data"]["id"]

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == admin.id,
            AuditLog.event_type == AuditEventType.RISK_SCORING_RULE_CREATED,
            AuditLog.resource_type == "risk_scoring_rule",
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )

    assert audit_log is not None
    assert audit_log.resource_id is not None
    assert str(audit_log.resource_id) == rule_id
