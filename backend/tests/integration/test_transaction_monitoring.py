import uuid

from app.models.audit_log import AuditLog
from app.models.transaction_monitoring_result import (
    TransactionMonitoringResult,
)
from app.utils.enums import (
    AuditEventType,
    UserRole,
)
from tests.helpers import authenticate_client


def create_transaction_aml_rule(
    client,
    *,
    name: str,
    condition: dict,
    severity: str = "HIGH",
    status: str = "ACTIVE",
):
    return client.post(
        "/api/v1/aml-rules",
        json={
            "name": name,
            "description": ("Transaction monitoring test rule."),
            "rule_type": "TRANSACTION",
            "condition": condition,
            "severity": severity,
            "status": status,
        },
    )


def test_matching_transaction_rule_generates_alert_and_stores_result(
    client,
    create_test_user,
    cleanup_transaction_monitoring_results,
    cleanup_aml_rules,
    db_session,
):
    admin = create_test_user(
        email=(f"transaction-monitoring-admin-{uuid.uuid4()}@example.com"),
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    rule_response = create_transaction_aml_rule(
        client,
        name="Large Transaction",
        condition={
            "field": "amount",
            "operator": ">=",
            "value": 10000,
        },
        severity="HIGH",
    )

    assert rule_response.status_code == 201

    rule_id = rule_response.json()["data"]["id"]

    transaction_id = uuid.uuid4()
    customer_id = uuid.uuid4()

    response = client.post(
        "/api/v1/transaction-monitoring/evaluate",
        json={
            "customer_id": str(customer_id),
            "transaction_id": str(transaction_id),
            "amount": "15000.00",
            "currency": "USD",
            "country": "US",
            "transaction_type": "TRANSFER",
            "transaction_date": "2026-09-27T12:00:00Z",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["transaction_id"] == str(transaction_id)
    assert data["customer_id"] == str(customer_id)
    assert data["evaluated_rule_count"] == 1
    assert data["matched_rule_count"] == 1
    assert data["alerts_generated"] == 1

    result = data["results"][0]

    assert result["rule_id"] == rule_id
    assert result["result"] == "MATCHED"
    assert result["alert_required"] is True

    stored_result = (
        db_session.query(TransactionMonitoringResult)
        .filter(
            TransactionMonitoringResult.transaction_id == transaction_id,
            TransactionMonitoringResult.rule_id == uuid.UUID(rule_id),
        )
        .first()
    )

    assert stored_result is not None
    assert stored_result.customer_id == customer_id
    assert stored_result.result.name == "MATCHED"

    db_session.expire_all()

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == admin.id,
            AuditLog.event_type == AuditEventType.AML_RULE_EVALUATED,
            AuditLog.resource_type == "aml_rule",
            AuditLog.resource_id == rule_id,
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )

    assert audit_log is not None


def test_non_matching_transaction_rule_stores_not_matched_result(
    client,
    create_test_user,
    cleanup_transaction_monitoring_results,
    cleanup_aml_rules,
    db_session,
):
    admin = create_test_user(
        email=(f"transaction-monitoring-no-match-{uuid.uuid4()}@example.com"),
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    rule_response = create_transaction_aml_rule(
        client,
        name="Large Transaction",
        condition={
            "field": "amount",
            "operator": ">=",
            "value": 10000,
        },
        severity="HIGH",
    )

    assert rule_response.status_code == 201

    transaction_id = uuid.uuid4()
    customer_id = uuid.uuid4()

    response = client.post(
        "/api/v1/transaction-monitoring/evaluate",
        json={
            "customer_id": str(customer_id),
            "transaction_id": str(transaction_id),
            "amount": "100.00",
            "currency": "USD",
            "country": "US",
            "transaction_type": "TRANSFER",
            "transaction_date": "2026-09-27T12:00:00Z",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["evaluated_rule_count"] == 1
    assert data["matched_rule_count"] == 0
    assert data["alerts_generated"] == 0

    result = data["results"][0]

    assert result["result"] == "NOT_MATCHED"
    assert result["alert_required"] is False

    stored_result = (
        db_session.query(TransactionMonitoringResult)
        .filter(
            TransactionMonitoringResult.transaction_id == transaction_id,
        )
        .first()
    )

    assert stored_result is not None
    assert stored_result.result.name == "NOT_MATCHED"


def test_inactive_transaction_rule_is_not_evaluated(
    client,
    create_test_user,
    cleanup_transaction_monitoring_results,
    cleanup_aml_rules,
):
    admin = create_test_user(
        email=(f"transaction-monitoring-inactive-{uuid.uuid4()}@example.com"),
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    rule_response = create_transaction_aml_rule(
        client,
        name="Inactive Large Transaction",
        condition={
            "field": "amount",
            "operator": ">=",
            "value": 10000,
        },
        severity="HIGH",
    )

    assert rule_response.status_code == 201

    rule_id = rule_response.json()["data"]["id"]

    deactivate_response = client.patch(
        f"/api/v1/aml-rules/{rule_id}/status",
        json={
            "status": "INACTIVE",
        },
    )

    assert deactivate_response.status_code == 200

    response = client.post(
        "/api/v1/transaction-monitoring/evaluate",
        json={
            "customer_id": str(uuid.uuid4()),
            "transaction_id": str(uuid.uuid4()),
            "amount": "15000.00",
            "currency": "USD",
            "country": "US",
            "transaction_type": "TRANSFER",
            "transaction_date": "2026-09-27T12:00:00Z",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["evaluated_rule_count"] == 0
    assert data["matched_rule_count"] == 0
    assert data["alerts_generated"] == 0
    assert data["results"] == []


def test_multiple_transaction_rules_store_multiple_results(
    client,
    create_test_user,
    cleanup_transaction_monitoring_results,
    cleanup_aml_rules,
    db_session,
):
    admin = create_test_user(
        email=(f"transaction-monitoring-multiple-{uuid.uuid4()}@example.com"),
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    high_amount_rule = create_transaction_aml_rule(
        client,
        name="High Amount",
        condition={
            "field": "amount",
            "operator": ">=",
            "value": 10000,
        },
        severity="HIGH",
    )

    assert high_amount_rule.status_code == 201

    high_risk_country_rule = create_transaction_aml_rule(
        client,
        name="High Risk Country",
        condition={
            "field": "country",
            "operator": "=",
            "value": "HIGH_RISK",
        },
        severity="CRITICAL",
    )

    assert high_risk_country_rule.status_code == 201

    transaction_id = uuid.uuid4()
    customer_id = uuid.uuid4()

    response = client.post(
        "/api/v1/transaction-monitoring/evaluate",
        json={
            "customer_id": str(customer_id),
            "transaction_id": str(transaction_id),
            "amount": "25000.00",
            "currency": "USD",
            "country": "HIGH_RISK",
            "transaction_type": "TRANSFER",
            "transaction_date": "2026-09-27T12:00:00Z",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["evaluated_rule_count"] == 2
    assert data["matched_rule_count"] == 2
    assert data["alerts_generated"] == 2

    assert len(data["results"]) == 2

    matched_results = [
        result for result in data["results"] if result["result"] == "MATCHED"
    ]

    assert len(matched_results) == 2

    stored_results = (
        db_session.query(TransactionMonitoringResult)
        .filter(
            TransactionMonitoringResult.transaction_id == transaction_id,
        )
        .all()
    )

    assert len(stored_results) == 2


def test_compliance_officer_can_evaluate_transaction(
    client,
    create_test_user,
    cleanup_transaction_monitoring_results,
    cleanup_aml_rules,
):
    admin = create_test_user(
        email=(f"transaction-monitoring-rbac-admin-{uuid.uuid4()}@example.com"),
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    rule_response = create_transaction_aml_rule(
        client,
        name="RBAC Transaction Rule",
        condition={
            "field": "amount",
            "operator": ">=",
            "value": 1000,
        },
        severity="MEDIUM",
    )

    assert rule_response.status_code == 201

    compliance_officer = create_test_user(
        email=(f"transaction-monitoring-compliance-{uuid.uuid4()}@example.com"),
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(client, compliance_officer)

    response = client.post(
        "/api/v1/transaction-monitoring/evaluate",
        json={
            "customer_id": str(uuid.uuid4()),
            "transaction_id": str(uuid.uuid4()),
            "amount": "1500.00",
            "currency": "USD",
            "country": "US",
            "transaction_type": "TRANSFER",
            "transaction_date": "2026-09-27T12:00:00Z",
        },
    )

    assert response.status_code == 200


def test_auditor_cannot_evaluate_transaction(
    client,
    create_test_user,
    cleanup_transaction_monitoring_results,
    cleanup_aml_rules,
):
    auditor = create_test_user(
        email=(f"transaction-monitoring-auditor-{uuid.uuid4()}@example.com"),
        role=UserRole.AUDITOR,
    )

    authenticate_client(client, auditor)

    response = client.post(
        "/api/v1/transaction-monitoring/evaluate",
        json={
            "customer_id": str(uuid.uuid4()),
            "transaction_id": str(uuid.uuid4()),
            "amount": "1500.00",
            "currency": "USD",
            "country": "US",
            "transaction_type": "TRANSFER",
            "transaction_date": "2026-09-27T12:00:00Z",
        },
    )

    assert response.status_code == 403
