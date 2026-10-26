"""Integration tests for account-scoped, synthetic sales demo scenarios."""

from uuid import UUID

from sqlalchemy import select

from app.core.config import settings
from app.models.sandbox import SandboxAccount
from app.utils.enums import UserRole
from tests.conftest import TestSessionLocal
from tests.helpers import authenticate_client


def test_sales_demo_account_dashboard_and_reset(client, create_test_user) -> None:
    previous_sandbox_enabled = settings.SANDBOX_ENABLED
    settings.SANDBOX_ENABLED = True
    account_ids: list[UUID] = []
    account_id: UUID | None = None
    try:
        sales_manager = create_test_user(
            role=UserRole.SALES_DEMO_MANAGER.value,
            email="sales-demo-manager@example.com",
        )
        authenticate_client(client, sales_manager)

        create_response = client.post(
            "/api/v1/sandbox/demo/accounts",
            json={
                "organization_name": "Meridian Demo Bank",
                "developer_name": "Demo Operator",
                "developer_email": "demo.operator@example.com",
            },
        )
        assert create_response.status_code == 201, create_response.text
        created = create_response.json()["data"]
        account_id = UUID(created["account"]["id"])
        account_ids.append(account_id)
        api_key = created["api_key"]
        assert api_key.startswith("fp_test_")
        assert created["scenario_count"] == 9
        assert len(created["sample_customers"]) == 4
        assert any(
            row["attributes"].get("customer_type") == "BUSINESS"
            for row in created["sample_customers"]
        )

        key_headers = {"X-API-Key": api_key}
        dashboard_response = client.get(
            "/api/v1/sandbox/demo/dashboard", headers=key_headers
        )
        assert dashboard_response.status_code == 200, dashboard_response.text
        dashboard = dashboard_response.json()["data"]
        assert dashboard["environment"] == "sales_demo"
        assert dashboard["is_synthetic"] is True
        assert dashboard["external_connections_enabled"] is False
        assert dashboard["customer_count"] == 4
        assert dashboard["individual_customer_count"] == 3
        assert dashboard["business_customer_count"] == 1
        assert dashboard["verification_count"] == 4
        assert dashboard["compliance_case_count"] == 2
        assert dashboard["aml_alert_count"] == 1
        assert dashboard["ai_recommendation_count"] == 1
        assert dashboard["scenario_record_count"] == 8

        alerts_response = client.get(
            "/api/v1/sandbox/demo/records?record_type=AML_ALERT",
            headers=key_headers,
        )
        assert alerts_response.status_code == 200, alerts_response.text
        alert_records = alerts_response.json()["data"]
        assert len(alert_records) == 1
        assert alert_records[0]["data"]["is_synthetic"] is True

        verification_examples = client.get(
            "/api/v1/sandbox/demo/verifications", headers=key_headers
        )
        assert verification_examples.status_code == 200
        assert len(verification_examples.json()["data"]) == 4

        read_key_response = client.post(
            "/api/v1/sandbox/account/api-keys",
            headers=key_headers,
            json={"name": "Read only demo key", "permissions": ["sandbox:read"]},
        )
        assert read_key_response.status_code == 201, read_key_response.text
        read_key = read_key_response.json()["data"]["api_key"]
        denied_reset = client.post(
            "/api/v1/sandbox/demo/reset", headers={"X-API-Key": read_key}
        )
        assert denied_reset.status_code == 403

        second_account_response = client.post(
            "/api/v1/sandbox/demo/accounts",
            json={
                "organization_name": "Atlas Demo Bank",
                "developer_name": "Second Demo Operator",
                "developer_email": "second.demo.operator@example.com",
            },
        )
        assert second_account_response.status_code == 201, second_account_response.text
        second_demo = second_account_response.json()["data"]
        second_account_id = UUID(second_demo["account"]["id"])
        account_ids.append(second_account_id)
        second_key = second_demo["api_key"]

        # Create user data, then prove reset restores only this demo account's seed.
        extra_customer = client.post(
            "/api/v1/sandbox/customers",
            headers=key_headers,
            json={
                "first_name": "Demo",
                "last_name": "Extra",
                "email": "extra.demo@example.com",
                "phone_number": "+15550101999",
                "attributes": {"customer_type": "INDIVIDUAL"},
            },
        )
        assert extra_customer.status_code == 201, extra_customer.text

        reset_response = client.post("/api/v1/sandbox/demo/reset", headers=key_headers)
        assert reset_response.status_code == 200, reset_response.text
        reset_dashboard = reset_response.json()["data"]
        assert reset_dashboard["customer_count"] == 4
        assert reset_dashboard["scenario_record_count"] == 8

        # The sandbox API key continues to work after reset, and another account
        # keeps its own state untouched.
        assert (
            client.get(
                "/api/v1/sandbox/demo/scenarios", headers=key_headers
            ).status_code
            == 200
        )
        second_dashboard = client.get(
            "/api/v1/sandbox/demo/dashboard",
            headers={"X-API-Key": second_key},
        )
        assert second_dashboard.status_code == 200, second_dashboard.text
        assert second_dashboard.json()["data"]["customer_count"] == 4
        assert second_dashboard.json()["data"]["scenario_record_count"] == 8
    finally:
        settings.SANDBOX_ENABLED = previous_sandbox_enabled
        db = TestSessionLocal()
        try:
            for cleanup_id in account_ids:
                account = db.scalar(
                    select(SandboxAccount).where(SandboxAccount.id == cleanup_id)
                )
                if account is not None:
                    db.delete(account)
            db.commit()
        finally:
            db.close()


def test_sales_demo_creation_requires_sales_demo_role(client, create_test_user) -> None:
    previous_sandbox_enabled = settings.SANDBOX_ENABLED
    settings.SANDBOX_ENABLED = True
    try:
        ordinary_user = create_test_user(
            role=UserRole.ANALYST.value,
            email="ordinary-analyst-demo-test@example.com",
        )
        authenticate_client(client, ordinary_user)
        response = client.post(
            "/api/v1/sandbox/demo/accounts",
            json={
                "organization_name": "Should Not Be Created",
                "developer_name": "Demo Operator",
                "developer_email": "forbidden.demo@example.com",
            },
        )
        assert response.status_code == 403, response.text
    finally:
        settings.SANDBOX_ENABLED = previous_sandbox_enabled


def test_demo_seed_data_is_static_and_uses_reserved_example_domains() -> None:
    from app.services.sales_demo_fixtures import (
        CUSTOMER_SEEDS,
        RECORD_SEEDS,
        SCENARIO_CATALOG,
    )

    assert len(CUSTOMER_SEEDS) == 4
    assert (
        sum(
            seed["attributes"].get("customer_type") == "BUSINESS"
            for seed in CUSTOMER_SEEDS
        )
        == 1
    )
    assert len({item["key"] for item in SCENARIO_CATALOG}) == len(SCENARIO_CATALOG)
    assert len({item["scenario_key"] for item in RECORD_SEEDS}) == len(RECORD_SEEDS)
    assert all(seed["email"].endswith("example.com") for seed in CUSTOMER_SEEDS)
    for record in RECORD_SEEDS:
        assert record["data"].get("is_synthetic", True) is True
        assert record["data"].get("external_provider_called", False) is False
