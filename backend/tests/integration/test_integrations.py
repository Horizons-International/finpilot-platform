from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.integrations.adapters.base import IntegrationAdapter, IntegrationCheckResult
from app.integrations.adapters.registry import adapter_registry
from app.models.audit_log import AuditLog
from app.models.integration import Integration
from app.utils.enums import IntegrationStatus, IntegrationType, UserRole


def authenticate_client(client: TestClient, user) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "Password123!"},
    )
    assert response.status_code == 200
    token = response.json()["data"]["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})


@pytest.fixture
def cleanup_integrations(db_session):
    initial_ids = set(db_session.scalars(select(Integration.id)).all())
    yield
    current_ids = set(db_session.scalars(select(Integration.id)).all())
    created_ids = list(current_ids - initial_ids)
    if created_ids:
        reason = "integration tests remove records created by this test"
        db_session.execute(
            delete(AuditLog)
            .where(
                AuditLog.resource_type == "integration",
                AuditLog.resource_id.in_(created_ids),
            )
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=reason,
            )
        )
        db_session.execute(
            delete(Integration)
            .where(Integration.id.in_(created_ids))
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=reason,
            )
        )
        db_session.commit()


def test_admin_can_create_configure_enable_and_check_integration(
    client: TestClient,
    create_test_user,
    cleanup_integrations,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "integration-admin@example.com",
    )
    authenticate_client(client, admin)

    response = client.post(
        "/api/v1/integrations",
        json={
            "provider_name": "mock",
            "integration_type": "BANKING",
            "configuration": {"base_url": "https://sandbox.example.test"},
        },
    )
    assert response.status_code == 201, response.text
    created = response.json()["data"]
    integration_id = created["id"]
    assert created["tenant_id"] == str(admin.tenant_id)
    assert created["is_enabled"] is False
    assert created["status"] == IntegrationStatus.UNKNOWN.value

    response = client.put(
        f"/api/v1/integrations/{integration_id}",
        json={
            "configuration": {
                "base_url": "https://sandbox.example.test",
                "timeout_seconds": 5,
            }
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["configuration"]["timeout_seconds"] == 5

    response = client.patch(
        f"/api/v1/integrations/{integration_id}/enabled",
        json={"is_enabled": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["is_enabled"] is True

    response = client.post(
        f"/api/v1/integrations/{integration_id}/check-connection",
    )
    assert response.status_code == 200, response.text
    result = response.json()["data"]
    assert result["integration"]["status"] == IntegrationStatus.DEGRADED.value
    assert result["integration"]["last_checked_at"] is not None
    assert "no live external connection" in result["message"].lower()

    response = client.get(
        "/api/v1/integrations?integration_type=BANKING&is_enabled=true"
    )
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["data"]] == [integration_id]

    response = client.patch(
        f"/api/v1/integrations/{integration_id}/enabled",
        json={"is_enabled": False},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["is_enabled"] is False


def test_plain_credentials_are_rejected_in_configuration(
    client: TestClient,
    create_test_user,
    cleanup_integrations,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "integration-secret-admin@example.com",
    )
    authenticate_client(client, admin)

    response = client.post(
        "/api/v1/integrations",
        json={
            "provider_name": "mock",
            "integration_type": "PAYMENT",
            "configuration": {"api_key": "do-not-store-this"},
        },
    )
    assert response.status_code == 422

    reference_response = client.post(
        "/api/v1/integrations",
        json={
            "provider_name": "mock",
            "integration_type": "PAYMENT",
            "configuration": {"api_key_secret_ref": "vault://sandbox/payments"},
        },
    )
    assert reference_response.status_code == 201, reference_response.text


def test_non_admin_cannot_manage_integrations(
    client: TestClient,
    create_test_user,
    cleanup_integrations,
):
    reviewer = create_test_user(
        UserRole.REVIEWER,
        "integration-reviewer@example.com",
    )
    authenticate_client(client, reviewer)
    response = client.get("/api/v1/integrations")
    assert response.status_code == 403


def test_integrations_are_isolated_between_tenants(
    client: TestClient,
    create_test_user,
    create_test_tenant,
    cleanup_integrations,
):
    tenant_a = create_test_tenant(name="Integration Tenant A")
    tenant_b = create_test_tenant(name="Integration Tenant B")
    admin_a = create_test_user(
        UserRole.ADMINISTRATOR,
        "integration-tenant-a@example.com",
        tenant_id=tenant_a.id,
    )
    admin_b = create_test_user(
        UserRole.ADMINISTRATOR,
        "integration-tenant-b@example.com",
        tenant_id=tenant_b.id,
    )

    authenticate_client(client, admin_a)
    response = client.post(
        "/api/v1/integrations",
        json={
            "provider_name": "mock",
            "integration_type": "DATA",
            "configuration": {"dataset": "tenant-a"},
        },
    )
    assert response.status_code == 201, response.text
    integration_id = response.json()["data"]["id"]
    assert UUID(integration_id)

    authenticate_client(client, admin_b)
    detail_response = client.get(f"/api/v1/integrations/{integration_id}")
    assert detail_response.status_code == 404

    list_response = client.get("/api/v1/integrations")
    assert list_response.status_code == 200
    assert integration_id not in {item["id"] for item in list_response.json()["data"]}


def test_adapter_connection_errors_are_recorded_without_leaking_secrets(
    client: TestClient,
    create_test_user,
    cleanup_integrations,
    monkeypatch,
):
    class FailingIntegrationAdapter(IntegrationAdapter):
        def validate_configuration(self) -> None:
            pass

        def check_connection(self) -> IntegrationCheckResult:
            raise RuntimeError(
                "Provider failed with client_secret=example-sensitive-value"
            )

    # Register this provider only for the duration of this test.
    monkeypatch.setitem(
        adapter_registry._factories,
        ("test-failing", IntegrationType.NOTIFICATION),
        FailingIntegrationAdapter,
    )

    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "integration-failure-admin@example.com",
    )
    authenticate_client(client, admin)

    create_response = client.post(
        "/api/v1/integrations",
        json={
            "provider_name": "test-failing",
            "integration_type": "NOTIFICATION",
            "configuration": {
                "endpoint": "https://invalid.example.test",
            },
        },
    )

    assert create_response.status_code == 201, create_response.text
    integration_id = create_response.json()["data"]["id"]

    response = client.post(
        f"/api/v1/integrations/{integration_id}/check-connection",
    )

    assert response.status_code == 200, response.text

    data = response.json()["data"]

    assert data["integration"]["status"] == IntegrationStatus.ERROR.value
    assert data["integration"]["last_error"]
    assert "example-sensitive-value" not in data["message"]
    assert "example-sensitive-value" not in data["integration"]["last_error"]
