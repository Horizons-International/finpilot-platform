"""Integration tests for AI transaction-risk analysis and stored history."""

from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from app.ai.schemas.responses import AIResponse
from app.utils.date_time import utc_now
from app.utils.enums import UserRole
from tests.helpers import authenticate_client, create_customer_with_data


def _observation(transaction_id, amount, when, destination="GB"):
    return {
        "transaction_id": str(transaction_id),
        "amount": str(amount),
        "currency": "GBP",
        "destination_country": destination,
        "transaction_type": "TRANSFER",
        "occurred_at": when.isoformat(),
    }


def test_ai_transaction_risk_analysis_persists_history_and_opens_case(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_ai_data,
):
    admin = create_test_user(
        email=f"ai-tx-risk-admin-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    officer = create_test_user(
        email=f"ai-tx-risk-{uuid4()}@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )
    authenticate_client(client, admin)
    customer_response = create_customer_with_data(
        client,
        email=f"ai-tx-risk-customer-{uuid4()}@example.com",
        country_of_residence="GB",
    )
    assert customer_response.status_code == 201, customer_response.text
    customer_id = customer_response.json()["data"]["id"]
    authenticate_client(client, officer)

    now = utc_now()
    historical = [_observation(uuid4(), "500.00", now - timedelta(days=30))]
    incoming = [
        _observation(uuid4(), "2000.00", now - timedelta(minutes=10 - index))
        for index in range(10)
    ]
    ai_response = AIResponse(
        provider_name="mock-test",
        request_type="transaction_risk_analysis",
        content="Ten transfers show a material deviation from the supplied baseline.",
        structured_data={
            "risk_score": 92,
            "reason": (
                "Ten recent transfers total GBP 20,000 "
                "against a GBP 500 baseline transaction."
            ),
            "recommended_action": (
                "Manual compliance review and verify source of funds."
            ),
            "risk_factors": [
                "Transaction value materially exceeds historical activity."
            ],
            "confidence": 0.93,
        },
        input_tokens=100,
        output_tokens=40,
    )
    with (
        patch(
            "app.services.transaction_risk_analysis_service.get_ai_provider",
            return_value=object(),
        ),
        patch(
            "app.services.transaction_risk_analysis_service.AIService.generate",
            return_value=ai_response,
        ),
    ):
        response = client.post(
            "/api/v1/transaction-risk-analysis/analyze",
            json={
                "customer_id": customer_id,
                "historical_transactions": historical,
                "transactions": incoming,
            },
        )

    assert response.status_code == 201, response.text
    result = response.json()["data"]
    assert result["risk_score"] == 92
    assert result["risk_level"] == "CRITICAL"
    assert result["compliance_case_id"] is not None
    assert result["transaction_summary"]["transaction_count"] == 10
    assert result["baseline_summary"]["transaction_count"] == 1
    assert "GBP" in result["transaction_summary"]["total_by_currency"]

    detail = client.get(f"/api/v1/transaction-risk-analysis/{result['id']}")
    assert detail.status_code == 200, detail.text
    history = client.get(
        "/api/v1/transaction-risk-analysis",
        params={"customer_id": customer_id},
    )
    assert history.status_code == 200, history.text
    assert any(item["id"] == result["id"] for item in history.json()["data"])


def test_ai_transaction_risk_rejects_duplicate_transaction_ids(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_ai_data,
):
    admin = create_test_user(
        email=f"ai-tx-risk-duplicate-admin-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    officer = create_test_user(
        email=f"ai-tx-risk-duplicate-{uuid4()}@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )
    authenticate_client(client, admin)
    customer_response = create_customer_with_data(
        client, email=f"ai-tx-risk-duplicate-customer-{uuid4()}@example.com"
    )
    assert customer_response.status_code == 201, customer_response.text
    customer_id = customer_response.json()["data"]["id"]
    authenticate_client(client, officer)
    shared_id = uuid4()
    observation = _observation(shared_id, "100.00", utc_now())
    ai_response = AIResponse(
        provider_name="mock-test",
        request_type="transaction_risk_analysis",
        content="Routine activity.",
        structured_data={
            "risk_score": 10,
            "reason": "The sample appears consistent with available behavior.",
            "recommended_action": "Continue routine monitoring.",
            "risk_factors": [],
            "confidence": 0.5,
        },
    )
    with (
        patch(
            "app.services.transaction_risk_analysis_service.get_ai_provider",
            return_value=object(),
        ),
        patch(
            "app.services.transaction_risk_analysis_service.AIService.generate",
            return_value=ai_response,
        ),
    ):
        first = client.post(
            "/api/v1/transaction-risk-analysis/analyze",
            json={"customer_id": customer_id, "transactions": [observation]},
        )
        assert first.status_code == 201, first.text
        second = client.post(
            "/api/v1/transaction-risk-analysis/analyze",
            json={"customer_id": customer_id, "transactions": [observation]},
        )
    assert second.status_code == 409, second.text
