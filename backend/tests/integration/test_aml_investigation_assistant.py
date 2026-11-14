"""Integration coverage for AI AML investigation assistance and history."""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from fastapi import HTTPException

from app.ai.exceptions import AIProviderError
from app.utils.enums import UserRole
from tests.helpers import authenticate_client, create_customer_with_data


def test_aml_investigation_returns_structured_response_and_sources(
    client,
    create_test_user,
    cleanup_ai_data,
    cleanup_test_customers,
    cleanup_aml_investigation_analyses,
):
    admin = create_test_user(
        email=f"aml-customer-creator-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    investigator = create_test_user(
        email=f"aml-investigator-{uuid4()}@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )
    authenticate_client(client, admin)
    customer_response = create_customer_with_data(
        client,
        email=f"aml-customer-{uuid4()}@example.com",
        country_of_residence="GB",
    )
    assert customer_response.status_code == 201, customer_response.text
    customer_id = customer_response.json()["data"]["id"]
    authenticate_client(client, investigator)

    response = client.post(
        "/api/v1/ai-assistant/aml-investigations/analyze",
        json={
            "question": "Review this customer and summarize the main AML risks.",
            "customer_id": customer_id,
            "retrieval_limit": 3,
        },
    )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["status"] == "COMPLETED"
    assert data["customer_id"] == customer_id
    assert data["result"]["summary"]
    assert isinstance(data["result"]["risk_indicators"], list)
    assert isinstance(data["result"]["related_activity"], list)
    assert isinstance(data["result"]["suggested_actions"], list)
    assert any(source["source_type"] == "customer" for source in data["sources"])
    analysis_id = data["id"]

    history = client.get(
        "/api/v1/ai-assistant/aml-investigations",
        params={"customer_id": customer_id},
    )
    assert history.status_code == 200, history.text
    assert history.json()["data"]["total"] >= 1
    assert any(item["id"] == analysis_id for item in history.json()["data"]["items"])

    detail = client.get(f"/api/v1/ai-assistant/aml-investigations/{analysis_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["sources"]


def test_aml_investigation_requires_customer_or_case(client, create_test_user):
    investigator = create_test_user(
        email=f"aml-no-target-{uuid4()}@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )
    authenticate_client(client, investigator)
    response = client.post(
        "/api/v1/ai-assistant/aml-investigations/analyze",
        json={"question": "Review this alert."},
    )
    assert response.status_code == 422


def test_aml_investigation_history_is_tenant_scoped(
    client,
    create_test_user,
    create_test_tenant,
    cleanup_ai_data,
    cleanup_test_customers,
    cleanup_aml_investigation_analyses,
):
    admin = create_test_user(
        email=f"aml-source-tenant-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, admin)
    customer_response = create_customer_with_data(
        client,
        email=f"aml-source-customer-{uuid4()}@example.com",
    )
    assert customer_response.status_code == 201, customer_response.text
    customer_id = customer_response.json()["data"]["id"]
    analysis_response = client.post(
        "/api/v1/ai-assistant/aml-investigations/analyze",
        json={
            "question": "Summarize the available AML investigation evidence.",
            "customer_id": customer_id,
        },
    )
    assert analysis_response.status_code == 201, analysis_response.text
    analysis_id = analysis_response.json()["data"]["id"]

    other_tenant = create_test_tenant()
    other_investigator = create_test_user(
        email=f"aml-other-tenant-{uuid4()}@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
        tenant_id=other_tenant.id,
    )
    authenticate_client(client, other_investigator)
    response = client.get(f"/api/v1/ai-assistant/aml-investigations/{analysis_id}")
    assert response.status_code == 404


def test_aml_investigation_checks_subscription_before_provider(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_aml_investigation_analyses,
):
    admin = create_test_user(
        email=f"aml-quota-admin-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    investigator = create_test_user(
        email=f"aml-quota-investigator-{uuid4()}@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )
    authenticate_client(client, admin)
    customer_response = create_customer_with_data(
        client, email=f"aml-quota-customer-{uuid4()}@example.com"
    )
    assert customer_response.status_code == 201, customer_response.text
    customer_id = customer_response.json()["data"]["id"]
    authenticate_client(client, investigator)

    quota_check = AsyncMock(
        side_effect=HTTPException(status_code=429, detail="Subscription limit reached.")
    )
    provider_factory = Mock(return_value=object())
    generate = AsyncMock()
    usage_record = AsyncMock()
    with (
        patch(
            "app.services.async_aml_investigation_assistant_service.record_subscription_usage",
            new=quota_check,
        ),
        patch(
            "app.services.async_aml_investigation_assistant_service.get_async_ai_provider",
            new=provider_factory,
        ),
        patch(
            "app.ai.services.async_ai_service.AsyncAIService.generate",
            new=generate,
        ),
        patch(
            "app.services.async_ai_usage_service.AsyncAIUsageService.record",
            new=usage_record,
        ),
    ):
        response = client.post(
            "/api/v1/ai-assistant/aml-investigations/analyze",
            json={
                "question": "Review this customer for AML risk.",
                "customer_id": customer_id,
            },
        )

    assert response.status_code == 429, response.text
    quota_check.assert_awaited_once()
    provider_factory.assert_not_called()
    generate.assert_not_awaited()
    usage_record.assert_not_awaited()


def test_aml_investigation_records_failed_provider_attempt(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_aml_investigation_analyses,
):
    admin = create_test_user(
        email=f"aml-provider-error-admin-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    investigator = create_test_user(
        email=f"aml-provider-error-investigator-{uuid4()}@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )
    authenticate_client(client, admin)
    customer_response = create_customer_with_data(
        client, email=f"aml-provider-error-customer-{uuid4()}@example.com"
    )
    assert customer_response.status_code == 201, customer_response.text
    customer_id = customer_response.json()["data"]["id"]
    authenticate_client(client, investigator)

    call_order = []

    async def reserve_allowance(*args, **kwargs):
        call_order.append("quota")

    async def fail_provider(*args, **kwargs):
        call_order.append("provider")
        raise AIProviderError("Mock provider failure.")

    quota_check = AsyncMock(side_effect=reserve_allowance)
    generate = AsyncMock(side_effect=fail_provider)
    usage_record = AsyncMock()
    with (
        patch(
            "app.services.async_aml_investigation_assistant_service.record_subscription_usage",
            new=quota_check,
        ),
        patch(
            "app.services.async_aml_investigation_assistant_service.get_async_ai_provider",
            new=Mock(return_value=object()),
        ),
        patch(
            "app.ai.services.async_ai_service.AsyncAIService.generate",
            new=generate,
        ),
        patch(
            "app.ai.services.async_ai_service.AsyncAIService.aclose",
            new=AsyncMock(),
        ),
        patch(
            "app.services.async_ai_usage_service.AsyncAIUsageService.record",
            new=usage_record,
        ),
    ):
        response = client.post(
            "/api/v1/ai-assistant/aml-investigations/analyze",
            json={
                "question": "Review this customer for AML risk.",
                "customer_id": customer_id,
            },
        )

    assert response.status_code == 503, response.text
    assert call_order == ["quota", "provider"]
    quota_check.assert_awaited_once()
    generate.assert_awaited_once()
    usage_record.assert_awaited_once()
    usage_arguments = usage_record.await_args.kwargs
    assert usage_arguments["feature"] == "AML_INVESTIGATION_ASSISTANT"
    assert usage_arguments["error_message"]
    assert usage_arguments["meter_subscription"] is False
    assert usage_arguments["commit"] is True
