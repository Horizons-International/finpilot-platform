import hashlib
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.models.api_key import APIKey
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.utils.enums import APIKeyStatus, AuditEventType, CustomerStatus, UserRole
from tests.helpers import authenticate_client


@pytest.fixture
def cleanup_api_key_data(db_session):
    existing_ids = set(
        db_session.scalars(
            select(APIKey.id).execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason="snapshot API keys for integration-test cleanup",
            )
        ).all()
    )
    yield
    created_keys = db_session.scalars(
        select(APIKey).execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason="find API keys created by an integration test",
        )
    ).all()
    for api_key in created_keys:
        if api_key.id in existing_ids:
            continue
        db_session.info["tenant_id"] = api_key.tenant_id
        db_session.query(AuditLog).filter(
            AuditLog.tenant_id == api_key.tenant_id,
            AuditLog.resource_type == "api_key",
            AuditLog.resource_id == api_key.id,
        ).delete(synchronize_session=False)
        db_session.delete(api_key)
        db_session.commit()
    db_session.info.pop("tenant_id", None)


def test_admin_can_generate_and_list_api_key(
    client,
    create_test_user,
    db_session,
    cleanup_api_key_data,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "api-key-create@example.com",
    )
    authenticate_client(client, admin)

    response = client.post(
        "/api/v1/api-keys",
        json={"name": "Core Banking Read Access", "permissions": ["customers:read"]},
    )
    assert response.status_code == 201
    created = response.json()["data"]
    raw_key = created["api_key"]
    api_key_id = created["id"]

    assert raw_key.startswith("fp_live_")
    assert created["permissions"] == ["customers:read"]
    assert created["status"] == APIKeyStatus.ACTIVE.value

    db_session.info["tenant_id"] = admin.tenant_id
    api_key = db_session.scalar(select(APIKey).where(APIKey.id == UUID(api_key_id)))
    assert api_key is not None
    assert api_key.key_hash == hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    assert raw_key not in api_key.key_hash

    listing = client.get("/api/v1/api-keys")
    assert listing.status_code == 200
    listed = next(item for item in listing.json()["data"] if item["id"] == api_key_id)
    assert "api_key" not in listed
    assert "key_hash" not in listed

    audit_events = db_session.scalars(
        select(AuditLog.event_type).where(
            AuditLog.tenant_id == admin.tenant_id,
            AuditLog.resource_type == "api_key",
            AuditLog.resource_id == UUID(api_key_id),
        )
    ).all()
    assert AuditEventType.API_KEY_CREATED in audit_events


def test_partner_api_key_requires_permission_and_records_usage(
    client,
    create_test_user,
    cleanup_api_key_data,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "api-key-permission@example.com",
    )
    authenticate_client(client, admin)

    response = client.post(
        "/api/v1/api-keys",
        json={"name": "Reports Only", "permissions": ["reports:read"]},
    )
    assert response.status_code == 201
    created = response.json()["data"]

    denied = client.get(
        "/api/v1/integrations/customers",
        headers={"X-API-Key": created["api_key"]},
    )
    assert denied.status_code == 403

    usage_response = client.get(f"/api/v1/api-keys/{created['id']}/usage")
    assert usage_response.status_code == 200
    usage = usage_response.json()["data"]
    assert len(usage) == 1
    assert usage[0]["method"] == "GET"
    assert usage[0]["path"] == "/api/v1/integrations/customers"
    assert usage[0]["status_code"] == 403


def test_api_key_can_call_scoped_customer_api_and_is_revoked(
    client,
    create_test_user,
    db_session,
    cleanup_api_key_data,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "api-key-revoke@example.com",
    )
    authenticate_client(client, admin)

    created_response = client.post(
        "/api/v1/api-keys",
        json={"name": "Customer Reader", "permissions": ["customers:read"]},
    )
    assert created_response.status_code == 201
    created = created_response.json()["data"]

    partner_response = client.get(
        "/api/v1/integrations/customers",
        headers={"X-API-Key": created["api_key"]},
    )
    assert partner_response.status_code == 200

    usage_response = client.get(f"/api/v1/api-keys/{created['id']}/usage")
    assert usage_response.status_code == 200
    recorded_statuses = {
        entry["status_code"] for entry in usage_response.json()["data"]
    }
    assert 200 in recorded_statuses

    revoke_response = client.post(f"/api/v1/api-keys/{created['id']}/revoke")
    assert revoke_response.status_code == 200
    assert revoke_response.json()["data"]["status"] == APIKeyStatus.REVOKED.value

    db_session.info["tenant_id"] = admin.tenant_id
    audit_events = db_session.scalars(
        select(AuditLog.event_type).where(
            AuditLog.tenant_id == admin.tenant_id,
            AuditLog.resource_type == "api_key",
            AuditLog.resource_id == UUID(created["id"]),
        )
    ).all()
    assert AuditEventType.API_KEY_CREATED in audit_events
    assert AuditEventType.API_KEY_REVOKED in audit_events

    rejected = client.get(
        "/api/v1/integrations/customers",
        headers={"X-API-Key": created["api_key"]},
    )
    assert rejected.status_code == 401


def test_api_key_management_is_restricted_to_tenant_administrators(
    client,
    create_test_user,
):
    viewer = create_test_user(
        UserRole.VIEWER,
        "api-key-viewer@example.com",
    )
    authenticate_client(client, viewer)

    response = client.post(
        "/api/v1/api-keys",
        json={"name": "Should Be Rejected", "permissions": ["customers:read"]},
    )
    assert response.status_code == 403


def test_api_key_cannot_read_another_tenants_customer(
    client,
    create_test_tenant,
    create_test_user,
    db_session,
    cleanup_api_key_data,
):
    tenant_a = create_test_tenant(name="API Key Tenant A")
    tenant_b = create_test_tenant(name="API Key Tenant B")
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "api-key-tenant-a@example.com",
        tenant_id=tenant_a.id,
    )
    authenticate_client(client, admin)

    created_response = client.post(
        "/api/v1/api-keys",
        json={"name": "Tenant A Reader", "permissions": ["customers:read"]},
    )
    assert created_response.status_code == 201
    raw_key = created_response.json()["data"]["api_key"]

    # Create a foreign-tenant customer in the test database.
    db_session.info["tenant_id"] = tenant_b.id
    foreign_customer = Customer(
        tenant_id=tenant_b.id,
        first_name="Foreign",
        last_name="Customer",
        email=f"foreign-customer-{uuid4()}@example.com",
        phone_number="+249912345679",
        status=CustomerStatus.NEW,
    )
    db_session.add(foreign_customer)
    db_session.commit()
    foreign_customer_id = foreign_customer.id
    db_session.info.pop("tenant_id", None)

    response = client.get(
        f"/api/v1/integrations/customers/{foreign_customer_id}",
        headers={"X-API-Key": raw_key},
    )
    assert response.status_code == 404
