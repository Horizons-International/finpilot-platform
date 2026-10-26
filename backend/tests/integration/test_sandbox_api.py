"""Integration coverage for isolated sandbox account and mock flows."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.sandbox import SandboxAccount
from app.utils.enums import UserRole
from tests.helpers import authenticate_client


@pytest.fixture
def sandbox_enabled(monkeypatch):
    monkeypatch.setattr(settings, "SANDBOX_ENABLED", True, raising=False)


@pytest.fixture
def cleanup_sandbox_accounts(db_session):
    existing = set(db_session.scalars(select(SandboxAccount.id)).all())
    yield
    ids = [
        account_id
        for account_id in db_session.scalars(select(SandboxAccount.id)).all()
        if account_id not in existing
    ]
    if ids:
        db_session.query(SandboxAccount).filter(SandboxAccount.id.in_(ids)).delete(
            synchronize_session=False
        )
        db_session.commit()


def _create_account(client, create_test_user):
    manager = create_test_user(
        role=UserRole.SALES_DEMO_MANAGER.value,
        email=f"sandbox-manager-{uuid4().hex}@example.com",
    )

    authenticate_client(client, manager)

    response = client.post(
        "/api/v1/sandbox/accounts",
        json={
            "organization_name": "Example Bank Sandbox",
            "developer_name": "Sandbox Developer",
            "developer_email": "developer@example.com",
        },
    )

    assert response.status_code == 201, response.text

    body = response.json()["data"]
    assert body["api_key"].startswith("fp_test_")
    assert len(body["sample_customers"]) == 3

    return body


def test_sandbox_is_disabled_by_default(client, monkeypatch):
    monkeypatch.setattr(settings, "SANDBOX_ENABLED", False, raising=False)
    response = client.post(
        "/api/v1/sandbox/accounts",
        json={
            "organization_name": "Disabled Sandbox",
            "developer_name": "Developer",
            "developer_email": "dev@example.com",
        },
    )
    assert response.status_code == 404


def test_sandbox_sample_customers_and_mock_verification(
    client, sandbox_enabled, cleanup_sandbox_accounts, create_test_user
):
    account = _create_account(client, create_test_user)
    headers = {"X-API-Key": account["api_key"]}
    response = client.get("/api/v1/sandbox/customers", headers=headers)
    assert response.status_code == 200, response.text
    customer = response.json()["data"][0]
    assert customer["sandbox_account_id"] == account["account"]["id"]

    response = client.post(
        f"/api/v1/sandbox/customers/{customer['id']}/verifications",
        headers=headers,
        json={"scenario": "MANUAL_REVIEW"},
    )
    assert response.status_code == 201, response.text
    result = response.json()["data"]
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["result"]["simulated"] is True
    assert result["result"]["provider"] == "FINPILOT_SANDBOX_MOCK"


def test_sandbox_webhook_is_simulated_without_network_delivery(
    client, sandbox_enabled, cleanup_sandbox_accounts, create_test_user
):
    account = _create_account(client, create_test_user)
    headers = {"X-API-Key": account["api_key"]}
    response = client.post(
        "/api/v1/sandbox/webhooks",
        headers=headers,
        json={
            "name": "Test receiver",
            "endpoint_url": "http://127.0.0.1:9000/hooks/finpilot",
            "event_types": ["customer.created"],
        },
    )
    assert response.status_code == 201, response.text
    webhook_id = response.json()["data"]["id"]
    customer_id = account["sample_customers"][0]["id"]
    response = client.post(
        f"/api/v1/sandbox/webhooks/{webhook_id}/simulate",
        headers=headers,
        json={
            "event_type": "customer.created",
            "customer_id": customer_id,
        },
    )
    assert response.status_code == 201, response.text
    event = response.json()["data"]
    assert event["delivery_status"] == "SIMULATED_NOT_SENT"
    assert event["payload"]["data"]["sandbox"] is True


def test_sandbox_keys_cannot_be_used_on_live_integration_routes(
    client, sandbox_enabled, cleanup_sandbox_accounts, create_test_user
):
    account = _create_account(client, create_test_user)
    response = client.get(
        "/api/v1/integrations/customers",
        headers={"X-API-Key": account["api_key"]},
    )
    assert response.status_code == 401


def test_sandbox_account_data_isolation(
    client, sandbox_enabled, cleanup_sandbox_accounts, create_test_user
):
    first = _create_account(client, create_test_user)
    second = _create_account(client, create_test_user)
    response = client.get(
        f"/api/v1/sandbox/customers/{first['sample_customers'][0]['id']}",
        headers={"X-API-Key": second["api_key"]},
    )
    assert response.status_code == 404


def test_sandbox_read_key_cannot_write(
    client, sandbox_enabled, cleanup_sandbox_accounts, create_test_user
):
    account = _create_account(client, create_test_user)
    admin_headers = {"X-API-Key": account["api_key"]}
    response = client.post(
        "/api/v1/sandbox/account/api-keys",
        headers=admin_headers,
        json={"name": "Read only", "permissions": ["sandbox:read"]},
    )
    assert response.status_code == 201, response.text
    read_key = response.json()["data"]["api_key"]
    response = client.post(
        "/api/v1/sandbox/customers",
        headers={"X-API-Key": read_key},
        json={
            "first_name": "Morgan",
            "last_name": "Example",
            "email": "morgan@example.com",
            "phone_number": "+15550101999",
        },
    )
    assert response.status_code == 403


def test_sandbox_users_can_be_created_and_listed(
    client, sandbox_enabled, cleanup_sandbox_accounts, create_test_user
):
    account = _create_account(client, create_test_user)
    headers = {"X-API-Key": account["api_key"]}
    response = client.post(
        "/api/v1/sandbox/users",
        headers=headers,
        json={
            "name": "Verification Reviewer",
            "email": "reviewer@example.com",
            "role": "REVIEWER",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["data"]["role"] == "REVIEWER"
    response = client.get("/api/v1/sandbox/users", headers=headers)
    assert response.status_code == 200, response.text
    assert len(response.json()["data"]) == 2
