import uuid
from unittest.mock import MagicMock

from app.models.aml_rule import AMLRule
from app.models.audit_log import AuditLog
from app.services.aml_rule_service import AMLRuleService
from app.utils.enums import (
    AMLRuleSeverity,
    AMLRuleStatus,
    AMLRuleType,
    AuditEventType,
    UserRole,
)
from tests.helpers import authenticate_client


def create_aml_rule(
    client,
    *,
    name: str = "High Risk Country",
    rule_type: str = "CUSTOMER_RISK",
    condition: dict | None = None,
    severity: str = "HIGH",
    status: str = "ACTIVE",
):
    if condition is None:
        condition = {
            "field": "country",
            "operator": "=",
            "value": "HIGH_RISK",
        }

    return client.post(
        "/api/v1/aml-rules",
        json={
            "name": name,
            "description": "Test AML rule",
            "rule_type": rule_type,
            "condition": condition,
            "severity": severity,
            "status": status,
        },
    )


def test_administrator_can_create_aml_rule(
    client,
    create_test_user,
    cleanup_aml_rules,
):
    admin = create_test_user(
        email=f"aml-rule-create-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    response = create_aml_rule(
        client,
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["name"] == "High Risk Country"
    assert data["rule_type"] == "CUSTOMER_RISK"
    assert data["severity"] == "HIGH"
    assert data["status"] == "ACTIVE"

    assert data["condition"] == {
        "field": "country",
        "operator": "=",
        "value": "HIGH_RISK",
    }


def test_created_aml_rule_is_audited(
    client,
    create_test_user,
    cleanup_aml_rules,
    db_session,
):
    admin = create_test_user(
        email=f"aml-rule-audit-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    response = create_aml_rule(
        client,
    )

    assert response.status_code == 201

    rule_id = response.json()["data"]["id"]

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == admin.id,
            AuditLog.event_type == AuditEventType.AML_RULE_CREATED,
            AuditLog.resource_type == "aml_rule",
        )
        .order_by(
            AuditLog.timestamp.desc(),
        )
        .first()
    )

    assert audit_log is not None
    assert audit_log.resource_id is not None
    assert str(audit_log.resource_id) == rule_id


def test_administrator_can_deactivate_aml_rule(
    client,
    create_test_user,
    cleanup_aml_rules,
):
    admin = create_test_user(
        email=f"aml-rule-disable-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    create_response = create_aml_rule(
        client,
    )

    assert create_response.status_code == 201

    rule_id = create_response.json()["data"]["id"]

    response = client.patch(
        f"/api/v1/aml-rules/{rule_id}/status",
        json={
            "status": "INACTIVE",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["id"] == rule_id
    assert data["status"] == "INACTIVE"


def test_administrator_can_reactivate_aml_rule(
    client,
    create_test_user,
    cleanup_aml_rules,
):
    admin = create_test_user(
        email=f"aml-rule-enable-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    create_response = create_aml_rule(
        client,
    )

    assert create_response.status_code == 201

    rule_id = create_response.json()["data"]["id"]

    disable_response = client.patch(
        f"/api/v1/aml-rules/{rule_id}/status",
        json={
            "status": "INACTIVE",
        },
    )

    assert disable_response.status_code == 200

    enable_response = client.patch(
        f"/api/v1/aml-rules/{rule_id}/status",
        json={
            "status": "ACTIVE",
        },
    )

    assert enable_response.status_code == 200

    data = enable_response.json()["data"]

    assert data["id"] == rule_id
    assert data["status"] == "ACTIVE"


def test_inactive_aml_rule_is_not_evaluated(
    client,
    create_test_user,
    cleanup_aml_rules,
):
    admin = create_test_user(
        email=f"aml-rule-inactive-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    create_response = create_aml_rule(
        client,
    )

    assert create_response.status_code == 201

    rule_id = create_response.json()["data"]["id"]

    disable_response = client.patch(
        f"/api/v1/aml-rules/{rule_id}/status",
        json={
            "status": "INACTIVE",
        },
    )

    assert disable_response.status_code == 200

    response = client.post(
        "/api/v1/aml-rules/evaluate",
        json={
            "rule_type": "CUSTOMER_RISK",
            "data": {
                "country": "HIGH_RISK",
            },
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["evaluated_rule_count"] == 0
    assert data["matched_rule_count"] == 0
    assert data["matches"] == []


def test_active_aml_rule_is_executed(
    client,
    create_test_user,
    cleanup_aml_rules,
    db_session,
):
    admin = create_test_user(
        email=f"aml-rule-execute-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    create_response = create_aml_rule(
        client,
        name="High Risk Country",
        condition={
            "field": "country",
            "operator": "=",
            "value": "HIGH_RISK",
        },
        severity="HIGH",
    )

    assert create_response.status_code == 201

    rule_id = create_response.json()["data"]["id"]

    response = client.post(
        "/api/v1/aml-rules/evaluate",
        json={
            "rule_type": "CUSTOMER_RISK",
            "data": {
                "country": "HIGH_RISK",
            },
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["rule_type"] == "CUSTOMER_RISK"
    assert data["evaluated_rule_count"] == 1
    assert data["matched_rule_count"] == 1

    assert len(data["evaluations"]) == 1
    assert data["evaluations"][0]["rule_id"] == rule_id
    assert data["evaluations"][0]["rule_name"] == ("High Risk Country")
    assert data["evaluations"][0]["matched"] is True

    assert len(data["matches"]) == 1

    match = data["matches"][0]

    assert match["rule_id"] == rule_id
    assert match["rule_name"] == "High Risk Country"
    assert match["severity"] == "HIGH"
    assert match["matched"] is True
    assert match["alert_required"] is True

    db_session.expire_all()

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == admin.id,
            AuditLog.event_type == AuditEventType.AML_RULE_EVALUATED,
            AuditLog.resource_type == "aml_rule",
            AuditLog.resource_id == rule_id,
        )
        .order_by(
            AuditLog.timestamp.desc(),
        )
        .first()
    )

    assert audit_log is not None


def test_aml_rule_execution_returns_no_match_when_condition_fails(
    client,
    create_test_user,
    cleanup_aml_rules,
):
    admin = create_test_user(
        email=f"aml-rule-no-match-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    create_response = create_aml_rule(
        client,
        condition={
            "field": "country",
            "operator": "=",
            "value": "HIGH_RISK",
        },
    )

    assert create_response.status_code == 201

    response = client.post(
        "/api/v1/aml-rules/evaluate",
        json={
            "rule_type": "CUSTOMER_RISK",
            "data": {
                "country": "LOW_RISK",
            },
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["evaluated_rule_count"] == 1
    assert data["matched_rule_count"] == 0
    assert data["matches"] == []


def test_rules_are_evaluated_by_rule_type(
    client,
    create_test_user,
    cleanup_aml_rules,
):
    admin = create_test_user(
        email=f"aml-rule-types-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    customer_rule = create_aml_rule(
        client,
        name="Customer Risk Rule",
        rule_type="CUSTOMER_RISK",
        condition={
            "field": "risk_level",
            "operator": "=",
            "value": "HIGH",
        },
    )

    transaction_rule = create_aml_rule(
        client,
        name="Large Transaction Rule",
        rule_type="TRANSACTION",
        condition={
            "field": "amount",
            "operator": ">",
            "value": 10000,
        },
    )

    verification_rule = create_aml_rule(
        client,
        name="Verification Rule",
        rule_type="VERIFICATION",
        condition={
            "field": "status",
            "operator": "=",
            "value": "MISSING",
        },
    )

    assert customer_rule.status_code == 201
    assert transaction_rule.status_code == 201
    assert verification_rule.status_code == 201

    response = client.post(
        "/api/v1/aml-rules/evaluate",
        json={
            "rule_type": "TRANSACTION",
            "data": {
                "amount": 15000,
            },
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["evaluated_rule_count"] == 1
    assert data["matched_rule_count"] == 1
    assert data["matches"][0]["rule_name"] == ("Large Transaction Rule")


def test_aml_rule_preserves_severity(
    client,
    create_test_user,
    cleanup_aml_rules,
):
    admin = create_test_user(
        email=f"aml-rule-severity-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    response = create_aml_rule(
        client,
        severity="CRITICAL",
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["severity"] == "CRITICAL"


def test_aml_rule_evaluation_returns_severity(
    client,
    create_test_user,
    cleanup_aml_rules,
):
    admin = create_test_user(
        email=f"aml-rule-severity-eval-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    create_response = create_aml_rule(
        client,
        severity="CRITICAL",
    )

    assert create_response.status_code == 201

    response = client.post(
        "/api/v1/aml-rules/evaluate",
        json={
            "rule_type": "CUSTOMER_RISK",
            "data": {
                "country": "HIGH_RISK",
            },
        },
    )

    assert response.status_code == 200

    match = response.json()["data"]["matches"][0]

    assert match["severity"] == "CRITICAL"


def test_invalid_aml_condition_is_rejected(
    client,
    create_test_user,
    cleanup_aml_rules,
):
    admin = create_test_user(
        email=f"aml-rule-invalid-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    response = create_aml_rule(
        client,
        condition={
            "field": "country",
            "operator": "CONTAINS",
            "value": "HIGH_RISK",
        },
    )

    assert response.status_code == 400


def test_aml_rule_requires_condition(
    client,
    create_test_user,
    cleanup_aml_rules,
):
    admin = create_test_user(
        email=f"aml-rule-empty-condition-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.post(
        "/api/v1/aml-rules",
        json={
            "name": "Invalid Rule",
            "description": "Invalid AML rule",
            "rule_type": "CUSTOMER_RISK",
            "condition": {},
            "severity": "HIGH",
            "status": "ACTIVE",
        },
    )

    assert response.status_code == 422


def test_compliance_officer_cannot_create_aml_rule(
    client,
    create_test_user,
    cleanup_aml_rules,
):
    compliance_officer = create_test_user(
        email=f"aml-rule-compliance-create-{uuid.uuid4()}@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(
        client,
        compliance_officer,
    )

    response = create_aml_rule(
        client,
    )

    assert response.status_code == 403


def test_compliance_officer_can_list_aml_rules(
    client,
    create_test_user,
    cleanup_aml_rules,
):
    compliance_officer = create_test_user(
        email=f"aml-rule-compliance-list-{uuid.uuid4()}@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(
        client,
        compliance_officer,
    )

    response = client.get(
        "/api/v1/aml-rules",
    )

    assert response.status_code == 200


def test_compliance_officer_can_evaluate_aml_rules(
    client,
    create_test_user,
    cleanup_aml_rules,
):
    compliance_officer = create_test_user(
        email=f"aml-rule-compliance-evaluate-{uuid.uuid4()}@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(
        client,
        compliance_officer,
    )

    response = client.post(
        "/api/v1/aml-rules/evaluate",
        json={
            "rule_type": "CUSTOMER_RISK",
            "data": {
                "country": "HIGH_RISK",
            },
        },
    )

    assert response.status_code == 200


def test_reviewer_cannot_create_aml_rule(
    client,
    create_test_user,
    cleanup_aml_rules,
):
    reviewer = create_test_user(
        email=f"aml-rule-reviewer-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(
        client,
        reviewer,
    )

    response = create_aml_rule(
        client,
    )

    assert response.status_code == 403


def test_auditor_cannot_create_aml_rule(
    client,
    create_test_user,
    cleanup_aml_rules,
):
    auditor = create_test_user(
        email=f"aml-rule-auditor-{uuid.uuid4()}@example.com",
        role=UserRole.AUDITOR,
    )

    authenticate_client(
        client,
        auditor,
    )

    response = create_aml_rule(
        client,
    )

    assert response.status_code == 403


def test_get_nonexistent_aml_rule_returns_404(
    client,
    create_test_user,
    cleanup_aml_rules,
):
    admin = create_test_user(
        email=f"aml-rule-not-found-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.get(
        "/api/v1/aml-rules/00000000-0000-0000-0000-000000000000",
    )

    assert response.status_code == 404


def test_update_nonexistent_aml_rule_status_returns_404(
    client,
    create_test_user,
    cleanup_aml_rules,
):
    admin = create_test_user(
        email=f"aml-rule-status-not-found-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.patch(
        "/api/v1/aml-rules/00000000-0000-0000-0000-000000000002/status",
        json={
            "status": "INACTIVE",
        },
    )

    assert response.status_code == 404


def test_aml_rule_rejects_duplicate_status_change(
    client,
    create_test_user,
    cleanup_aml_rules,
):
    admin = create_test_user(
        email=f"aml-rule-status-duplicate-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    create_response = create_aml_rule(
        client,
    )

    assert create_response.status_code == 201

    rule_id = create_response.json()["data"]["id"]

    first_response = client.patch(
        f"/api/v1/aml-rules/{rule_id}/status",
        json={
            "status": "INACTIVE",
        },
    )

    assert first_response.status_code == 200

    second_response = client.patch(
        f"/api/v1/aml-rules/{rule_id}/status",
        json={
            "status": "INACTIVE",
        },
    )

    assert second_response.status_code == 400


def test_aml_rule_status_change_is_audited(
    client,
    create_test_user,
    cleanup_aml_rules,
    db_session,
):
    admin = create_test_user(
        email=f"aml-rule-status-audit-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    create_response = create_aml_rule(
        client,
    )

    assert create_response.status_code == 201

    rule_id = create_response.json()["data"]["id"]

    response = client.patch(
        f"/api/v1/aml-rules/{rule_id}/status",
        json={
            "status": "INACTIVE",
        },
    )

    assert response.status_code == 200

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == admin.id,
            AuditLog.event_type == AuditEventType.AML_RULE_STATUS_CHANGED,
            AuditLog.resource_type == "aml_rule",
        )
        .order_by(
            AuditLog.timestamp.desc(),
        )
        .first()
    )

    assert audit_log is not None
    assert audit_log.resource_id is not None
    assert str(audit_log.resource_id) == rule_id


def test_matched_aml_rule_evaluation_is_audited(
    client,
    create_test_user,
    cleanup_aml_rules,
    db_session,
):
    admin = create_test_user(
        email=f"aml-rule-evaluated-audit-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    create_response = create_aml_rule(
        client,
    )

    assert create_response.status_code == 201

    rule_id = create_response.json()["data"]["id"]

    response = client.post(
        "/api/v1/aml-rules/evaluate",
        json={
            "rule_type": "CUSTOMER_RISK",
            "data": {
                "country": "HIGH_RISK",
            },
        },
    )

    assert response.status_code == 200

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == admin.id,
            AuditLog.event_type == AuditEventType.AML_RULE_EVALUATED,
            AuditLog.resource_type == "aml_rule",
            AuditLog.resource_id == rule_id,
        )
        .order_by(
            AuditLog.timestamp.desc(),
        )
        .first()
    )

    assert audit_log is not None


def test_non_matching_aml_rule_is_evaluated_and_audited(
    client,
    create_test_user,
    cleanup_aml_rules,
    db_session,
):
    admin = create_test_user(
        email=f"aml-rule-non-match-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    create_response = create_aml_rule(
        client,
        name="High Risk Country",
        condition={
            "field": "country",
            "operator": "=",
            "value": "HIGH_RISK",
        },
        severity="HIGH",
    )

    assert create_response.status_code == 201

    rule_id = create_response.json()["data"]["id"]

    response = client.post(
        "/api/v1/aml-rules/evaluate",
        json={
            "rule_type": "CUSTOMER_RISK",
            "data": {
                "country": "LOW_RISK",
            },
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["evaluated_rule_count"] == 1
    assert data["matched_rule_count"] == 0
    assert data["matches"] == []

    assert len(data["evaluations"]) == 1

    evaluation = data["evaluations"][0]

    assert evaluation["rule_id"] == rule_id
    assert evaluation["matched"] is False

    db_session.expire_all()

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == admin.id,
            AuditLog.event_type == AuditEventType.AML_RULE_EVALUATED,
            AuditLog.resource_type == "aml_rule",
            AuditLog.resource_id == rule_id,
        )
        .order_by(
            AuditLog.timestamp.desc(),
        )
        .first()
    )

    assert audit_log is not None


def test_inactive_aml_rule_is_not_evaluated_or_audited(
    client,
    create_test_user,
    cleanup_aml_rules,
    db_session,
):
    admin = create_test_user(
        email=f"aml-rule-inactive-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    create_response = create_aml_rule(
        client,
        name="High Risk Country",
        condition={
            "field": "country",
            "operator": "=",
            "value": "HIGH_RISK",
        },
    )

    assert create_response.status_code == 201

    rule_id = create_response.json()["data"]["id"]

    disable_response = client.patch(
        f"/api/v1/aml-rules/{rule_id}/status",
        json={
            "status": "INACTIVE",
        },
    )

    assert disable_response.status_code == 200

    response = client.post(
        "/api/v1/aml-rules/evaluate",
        json={
            "rule_type": "CUSTOMER_RISK",
            "data": {
                "country": "HIGH_RISK",
            },
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["evaluated_rule_count"] == 0
    assert data["matched_rule_count"] == 0
    assert data["evaluations"] == []
    assert data["matches"] == []

    db_session.expire_all()

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == admin.id,
            AuditLog.event_type == AuditEventType.AML_RULE_EVALUATED,
            AuditLog.resource_type == "aml_rule",
            AuditLog.resource_id == rule_id,
        )
        .first()
    )

    assert audit_log is None


def test_aml_rule_service_evaluate_creates_audit_and_commits():
    db = MagicMock()

    service = AMLRuleService(
        db,
    )

    rule = AMLRule(
        id=uuid.uuid4(),
        name="High Risk Country",
        description="Test",
        rule_type=AMLRuleType.CUSTOMER_RISK,
        condition={
            "field": "country",
            "operator": "=",
            "value": "HIGH_RISK",
        },
        severity=AMLRuleSeverity.HIGH,
        status=AMLRuleStatus.ACTIVE,
    )

    service.repository.get_active_by_type = MagicMock(
        return_value=[rule],
    )

    service.audit_service.log_event = MagicMock()

    result = service.evaluate(
        rule_type=AMLRuleType.CUSTOMER_RISK,
        data={
            "country": "HIGH_RISK",
        },
        user_id=uuid.uuid4(),
        email="admin@example.com",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert result.evaluated_rule_count == 1
    assert result.matched_rule_count == 1

    service.audit_service.log_event.assert_called_once()

    audit_call = service.audit_service.log_event.call_args.kwargs

    assert audit_call["event_type"] == AuditEventType.AML_RULE_EVALUATED

    assert audit_call["resource_type"] == "aml_rule"
    assert audit_call["resource_id"] == rule.id

    db.commit.assert_called_once()
