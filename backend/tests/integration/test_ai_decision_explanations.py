from uuid import UUID

import pytest
from sqlalchemy import select

from app.models.ai_decision_explanation import AIDecisionExplanation
from tests.conftest import TestSessionLocal
from tests.helpers import authenticate_client, create_customer_with_data


@pytest.fixture
def cleanup_ai_decision_explanations():
    db = TestSessionLocal()
    try:
        before_ids = set(db.scalars(select(AIDecisionExplanation.id)).all())
    finally:
        db.close()

    yield

    cleanup_db = TestSessionLocal()
    try:
        after_ids = set(cleanup_db.scalars(select(AIDecisionExplanation.id)).all())
        created_ids = after_ids - before_ids
        if created_ids:
            (
                cleanup_db.query(AIDecisionExplanation)
                .filter(AIDecisionExplanation.id.in_(created_ids))
                .delete(synchronize_session=False)
            )
            cleanup_db.commit()
    finally:
        cleanup_db.close()


def test_case_priority_explanation_and_history_are_available(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_ai_decision_explanations,
):
    user = create_test_user(
        email="case-explainability@example.com",
        role="Administrator",
    )
    authenticate_client(client, user)

    customer_response = create_customer_with_data(
        client,
        first_name="Explainability",
        email="explainability-customer@example.com",
    )
    assert customer_response.status_code == 201
    customer_id = customer_response.json()["data"]["id"]

    case_response = client.post(
        "/api/v1/compliance-cases",
        json={
            "customer_id": customer_id,
            "case_type": "MANUAL_INVESTIGATION",
            "priority": "HIGH",
            "description": "Test case for explanation capture.",
        },
    )
    assert case_response.status_code == 201, case_response.text
    case_id = case_response.json()["data"]["id"]

    priority_response = client.post(f"/api/v1/case-priorities/{case_id}/recalculate")
    assert priority_response.status_code == 200, priority_response.text
    priority_id = priority_response.json()["data"]["id"]

    explanation_response = client.get(
        f"/api/v1/ai-assistant/decision-explanations/CASE_PRIORITY/{priority_id}"
    )
    assert explanation_response.status_code == 200, explanation_response.text
    explanation = explanation_response.json()["data"]
    assert explanation["decision_type"] == "CASE_PRIORITY"
    assert explanation["decision_id"] == priority_id
    assert explanation["factors"]
    assert explanation["data_sources"]
    assert explanation["risk_indicators"]
    assert explanation["confidence_score"] is not None
    assert "Case alert severity" in explanation["recommendation_reason"]

    history_path = (
        "/api/v1/ai-assistant/decision-explanations/CASE_PRIORITY/"
        f"{priority_id}/history"
    )
    history_response = client.get(history_path)
    assert history_response.status_code == 200, history_response.text
    history = history_response.json()["data"]
    assert history["total"] >= 1
    assert history["items"][0]["decision_id"] == str(UUID(priority_id))
