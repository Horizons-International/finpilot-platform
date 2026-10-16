from datetime import datetime, timezone
from uuid import uuid4

from app.models.customer_risk_profile import CustomerRiskProfile
from app.utils.enums import ComplianceCasePriority, CustomerRiskLevel, UserRole
from tests.helpers import authenticate_client, create_customer_with_data


def _create_compliance_case(client, customer_id, priority="MEDIUM"):
    response = client.post(
        "/api/v1/compliance-cases",
        json={
            "customer_id": customer_id,
            "case_type": "AML_ALERT",
            "priority": priority,
            "description": "Test case for priority scoring.",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def test_priority_endpoint_returns_score_snapshot_and_reason(
    client, create_test_user, cleanup_test_customers
):
    admin = create_test_user(
        email=f"case-priority-{uuid4()}@example.com", role=UserRole.ADMINISTRATOR
    )
    authenticate_client(client, admin)
    customer_response = create_customer_with_data(
        client, email=f"priority-{uuid4()}@example.com"
    )
    assert customer_response.status_code == 201, customer_response.text
    customer_id = customer_response.json()["data"]["id"]
    case_id = _create_compliance_case(client, customer_id, priority="CRITICAL")

    response = client.get(f"/api/v1/case-priorities/{case_id}")
    assert response.status_code == 200, response.text
    result = response.json()["data"]
    assert 0 <= float(result["priority_score"]) <= 100
    assert result["priority_level"] == ComplianceCasePriority.CRITICAL.value
    assert "alert severity" in result["reason"].lower()
    assert result["risk_snapshot"]["case_id"] == case_id
    assert result["risk_snapshot"]["signals"]["alert_severity"] == 95.0


def test_priority_refreshes_when_customer_risk_profile_changes(
    client, db_session, create_test_user, cleanup_test_customers
):
    admin = create_test_user(
        email=f"case-priority-refresh-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, admin)
    customer_response = create_customer_with_data(
        client, email=f"priority-refresh-{uuid4()}@example.com"
    )
    assert customer_response.status_code == 201, customer_response.text
    customer_id = customer_response.json()["data"]["id"]
    case_id = _create_compliance_case(client, customer_id, priority="MEDIUM")

    first = client.get(f"/api/v1/case-priorities/{case_id}")
    assert first.status_code == 200, first.text
    first_score = float(first.json()["data"]["priority_score"])

    db_session.info["tenant_id"] = admin.tenant_id
    profile = CustomerRiskProfile(
        tenant_id=admin.tenant_id,
        customer_id=customer_id,
        risk_level=CustomerRiskLevel.HIGH,
        risk_score=92,
        risk_category="HIGH_VALUE_ACTIVITY",
        assessed_at=datetime.now(timezone.utc),
        assessment_source="integration-test",
        calculation_details={"geographic_risk_score": 70},
    )
    db_session.add(profile)
    db_session.commit()

    refreshed = client.get(f"/api/v1/case-priorities/{case_id}")
    assert refreshed.status_code == 200, refreshed.text
    assert float(refreshed.json()["data"]["priority_score"]) != first_score

    history = client.get(f"/api/v1/case-priorities/{case_id}/history")
    assert history.status_code == 200, history.text
    assert len(history.json()["data"]) == 2
