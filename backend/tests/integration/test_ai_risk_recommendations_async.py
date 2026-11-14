"""Integration coverage for native-async AI risk recommendations."""

from uuid import UUID, uuid4

import pytest

from app.models.ai_risk_recommendation import AIRiskRecommendation
from app.utils.enums import UserRole
from tests.conftest import TestSessionLocal
from tests.helpers import authenticate_client, create_customer_with_data


@pytest.fixture
def cleanup_ai_risk_recommendations():
    setup_db = TestSessionLocal()
    existing_recommendation_ids = {
        row.id for row in setup_db.query(AIRiskRecommendation.id).all()
    }
    setup_db.close()

    yield

    cleanup_db = TestSessionLocal()
    try:
        new_recommendations = (
            cleanup_db.query(AIRiskRecommendation)
            .filter(~AIRiskRecommendation.id.in_(existing_recommendation_ids))
            .all()
        )
        for recommendation in new_recommendations:
            cleanup_db.delete(recommendation)

        cleanup_db.commit()
    finally:
        cleanup_db.close()


def test_ai_risk_recommendation_generate_and_history_are_async_backed(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_ai_risk_recommendations,
):
    administrator = create_test_user(
        email=f"async-risk-recommendation-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, administrator)
    customer_response = create_customer_with_data(
        client,
        email=f"async-risk-customer-{uuid4()}@example.com",
        country_of_residence="GB",
    )
    assert customer_response.status_code == 201, customer_response.text
    customer_id = customer_response.json()["data"]["id"]

    response = client.post(
        "/api/v1/ai-risk-recommendations",
        json={"customer_id": customer_id},
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    recommendation_id = data["id"]

    assert 0 <= float(data["risk_score"]) <= 100
    assert data["risk_level"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert data["required_review_type"]
    assert data["risk_factors"]
    assert data["input_snapshot"]["customer"]["id"] == customer_id
    assert data["provider_name"] in {"mock", "openai", "deterministic_rules"}

    history = client.get(
        "/api/v1/ai-risk-recommendations",
        params={"customer_id": customer_id},
    )
    assert history.status_code == 200, history.text
    assert history.json()["data"]["total"] >= 1
    assert any(
        item["id"] == recommendation_id for item in history.json()["data"]["items"]
    )

    detail = client.get(f"/api/v1/ai-risk-recommendations/{recommendation_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["id"] == recommendation_id


def test_ai_risk_recommendation_detail_is_tenant_scoped(
    client,
    create_test_user,
    create_test_tenant,
    cleanup_test_customers,
    cleanup_ai_risk_recommendations,
):
    administrator = create_test_user(
        email=f"async-risk-owner-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, administrator)
    customer_response = create_customer_with_data(
        client,
        email=f"async-risk-owner-customer-{uuid4()}@example.com",
    )
    assert customer_response.status_code == 201, customer_response.text
    customer_id = customer_response.json()["data"]["id"]
    generated = client.post(
        "/api/v1/ai-risk-recommendations",
        json={"customer_id": customer_id},
    )
    assert generated.status_code == 201, generated.text
    recommendation_id = generated.json()["data"]["id"]

    other_tenant = create_test_tenant()
    other_viewer = create_test_user(
        email=f"async-risk-other-tenant-{uuid4()}@example.com",
        role=UserRole.VIEWER,
        tenant_id=other_tenant.id,
    )
    authenticate_client(client, other_viewer)
    response = client.get(f"/api/v1/ai-risk-recommendations/{UUID(recommendation_id)}")
    assert response.status_code == 404
