"""Integration coverage for native-async AI risk recommendations."""

from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.ai.exceptions import AIProviderError
from app.ai.schemas.responses import AIResponse
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


def _create_risk_recommendation_customer(
    client, create_test_user, *, prefix: str
) -> str:
    administrator = create_test_user(
        email=f"{prefix}-admin-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, administrator)
    customer_response = create_customer_with_data(
        client,
        email=f"{prefix}-customer-{uuid4()}@example.com",
        country_of_residence="GB",
    )
    assert customer_response.status_code == 201, customer_response.text
    return str(customer_response.json()["data"]["id"])


def test_ai_risk_recommendation_checks_quota_before_provider_call(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_ai_risk_recommendations,
):
    customer_id = _create_risk_recommendation_customer(
        client, create_test_user, prefix="async-risk-quota"
    )
    quota_error = HTTPException(
        status_code=429,
        detail="Subscription limit reached for 'ai_requests'.",
        headers={"X-Subscription-Metric": "ai_requests"},
    )

    with (
        patch(
            "app.services.async_ai_risk_recommendation_service."
            "record_subscription_usage",
            new=AsyncMock(side_effect=quota_error),
        ) as reserve_quota,
        patch(
            "app.services.async_ai_risk_recommendation_service.get_async_ai_provider"
        ) as get_provider,
    ):
        response = client.post(
            "/api/v1/ai-risk-recommendations",
            json={"customer_id": customer_id},
        )

    assert response.status_code == 429, response.text
    reserve_quota.assert_awaited_once()
    get_provider.assert_not_called()


def test_ai_risk_recommendation_records_failed_provider_attempt_and_uses_fallback(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_ai_risk_recommendations,
):
    customer_id = _create_risk_recommendation_customer(
        client, create_test_user, prefix="async-risk-provider-failure"
    )

    with (
        patch(
            "app.services.async_ai_risk_recommendation_service."
            "record_subscription_usage",
            new=AsyncMock(),
        ) as reserve_quota,
        patch(
            "app.services.async_ai_risk_recommendation_service.get_async_ai_provider",
            return_value=object(),
        ),
        patch(
            "app.ai.services.async_ai_service.AsyncAIService.generate",
            new=AsyncMock(side_effect=AIProviderError("provider unavailable")),
        ),
        patch(
            "app.ai.services.async_ai_service.AsyncAIService.aclose",
            new=AsyncMock(),
        ),
        patch(
            "app.services.async_ai_risk_recommendation_service."
            "AsyncAIUsageService.record",
            new=AsyncMock(),
        ) as record_usage,
    ):
        response = client.post(
            "/api/v1/ai-risk-recommendations",
            json={"customer_id": customer_id},
        )

    assert response.status_code == 201, response.text
    assert response.json()["data"]["provider_name"] == "deterministic_rules"
    reserve_quota.assert_awaited_once()
    record_usage.assert_awaited_once()
    usage_call = record_usage.await_args
    assert usage_call is not None
    usage_kwargs = usage_call.kwargs
    assert usage_kwargs["feature"] == "AI_RISK_RECOMMENDATION"
    assert usage_kwargs["error_message"].startswith("AIProviderError:")
    assert usage_kwargs["commit"] is True
    assert usage_kwargs["meter_subscription"] is False


def test_ai_risk_recommendation_records_successful_provider_usage(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_ai_risk_recommendations,
):
    customer_id = _create_risk_recommendation_customer(
        client, create_test_user, prefix="async-risk-provider-success"
    )
    ai_response = AIResponse(
        provider_name="mock-test",
        request_type="transaction_risk_analysis",
        content="A measured risk assessment based on stored evidence.",
        structured_data={
            "risk_score": 42,
            "reason": "The available records indicate a moderate review signal.",
            "recommended_action": "Review the identified indicators.",
            "risk_factors": ["A stored risk indicator is present."],
            "confidence": 0.8,
        },
        input_tokens=120,
        output_tokens=45,
    )

    with (
        patch(
            "app.services.async_ai_risk_recommendation_service."
            "record_subscription_usage",
            new=AsyncMock(),
        ) as reserve_quota,
        patch(
            "app.services.async_ai_risk_recommendation_service.get_async_ai_provider",
            return_value=object(),
        ),
        patch(
            "app.ai.services.async_ai_service.AsyncAIService.generate",
            new=AsyncMock(return_value=ai_response),
        ),
        patch(
            "app.ai.services.async_ai_service.AsyncAIService.aclose",
            new=AsyncMock(),
        ),
        patch(
            "app.services.async_ai_risk_recommendation_service."
            "AsyncAIUsageService.record",
            new=AsyncMock(),
        ) as record_usage,
    ):
        response = client.post(
            "/api/v1/ai-risk-recommendations",
            json={"customer_id": customer_id},
        )

    assert response.status_code == 201, response.text
    assert response.json()["data"]["provider_name"] == "mock-test"
    reserve_quota.assert_awaited_once()
    record_usage.assert_awaited_once()
    usage_call = record_usage.await_args
    assert usage_call is not None
    usage_kwargs = usage_call.kwargs
    assert usage_kwargs["feature"] == "AI_RISK_RECOMMENDATION"
    assert usage_kwargs["input_tokens"] == 120
    assert usage_kwargs["output_tokens"] == 45
    assert usage_kwargs["error_message"] is None
    assert usage_kwargs["commit"] is True
    assert usage_kwargs["meter_subscription"] is False
