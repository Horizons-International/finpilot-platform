from uuid import uuid4

from app.utils.enums import (
    TenantStatus,
    UserRole,
)
from tests.helpers import authenticate_client


def test_platform_admin_can_create_tenant(
    client,
    create_test_user,
):
    platform_admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"platform-{uuid4()}@example.com",
        is_platform_admin=True,
    )

    authenticate_client(
        client,
        platform_admin,
    )

    response = client.post(
        "/api/v1/tenants",
        json={
            "name": "Bank A",
            "code": f"BANKA-{uuid4().hex[:6].upper()}",
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["name"] == "Bank A"
    assert data["status"] == TenantStatus.ACTIVE.value
    assert data["code"].startswith("BANKA-")


def test_tenant_is_present_in_login_response(
    client,
    create_test_user,
):
    user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"tenant-login-{uuid4()}@example.com",
    )

    authenticate_client(
        client,
        user,
    )

    response = client.get(
        "/api/v1/tenants/me",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert str(data["id"]) == str(user.tenant_id)


def test_users_belong_to_tenants(
    client,
    create_test_tenant,
    create_test_user,
):
    tenant = create_test_tenant(
        name="Tenant B",
        code=f"TENANT-B-{uuid4().hex[:6].upper()}",
    )

    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"tenant-admin-{uuid4()}@example.com",
        is_platform_admin=True,
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.post(
        "/api/v1/users",
        json={
            "first_name": "Tenant",
            "last_name": "User",
            "email": f"tenant-user-{uuid4()}@example.com",
            "password": "Password123!",
            "role": "Reviewer",
            "tenant_id": str(tenant.id),
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert str(data["tenant_id"]) == str(tenant.id)


def test_customer_data_is_isolated_by_tenant(
    client,
    create_test_tenant,
    create_test_user,
    create_test_customer,
):
    tenant_a = create_test_tenant(
        code=f"TENANT-A-{uuid4().hex[:8].upper()}",
    )

    tenant_b = create_test_tenant(
        code=f"TENANT-B-{uuid4().hex[:8].upper()}",
    )

    tenant_a_user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"tenant-a-{uuid4()}@example.com",
        tenant_id=tenant_a.id,
    )

    tenant_b_user = create_test_user(  # noqa: F841
        role=UserRole.ADMINISTRATOR,
        email=f"tenant-b-{uuid4()}@example.com",
        tenant_id=tenant_b.id,
    )

    tenant_b_customer = create_test_customer(
        tenant_id=tenant_b.id,
        email=f"tenant-b-customer-{uuid4()}@example.com",
    )

    authenticate_client(
        client,
        tenant_a_user,
    )

    response = client.get(
        f"/api/v1/customers/{tenant_b_customer.id}",
    )

    assert response.status_code == 404


def test_workflow_names_are_scoped_to_tenant(
    client,
    create_test_tenant,
    create_test_user,
):
    tenant_a = create_test_tenant(
        code=f"TENANT-A-{uuid4().hex[:8].upper()}",
    )

    tenant_b = create_test_tenant(
        code=f"TENANT-B-{uuid4().hex[:8].upper()}",
    )

    tenant_a_user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"workflow-a-{uuid4()}@example.com",
        tenant_id=tenant_a.id,
    )

    tenant_b_user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"workflow-b-{uuid4()}@example.com",
        tenant_id=tenant_b.id,
    )

    authenticate_client(
        client,
        tenant_a_user,
    )

    response_a = client.post(
        "/api/v1/workflows",
        json={
            "name": "Customer Onboarding",
            "description": "Tenant A workflow",
        },
    )

    assert response_a.status_code == 201

    authenticate_client(
        client,
        tenant_b_user,
    )

    response_b = client.post(
        "/api/v1/workflows",
        json={
            "name": "Customer Onboarding",
            "description": "Tenant B workflow",
        },
    )

    assert response_b.status_code == 201


def test_system_configuration_keys_are_scoped_to_tenant(
    client,
    create_test_tenant,
    create_test_user,
):
    tenant_a = create_test_tenant(
        code=f"TENANT-A-{uuid4().hex[:8].upper()}",
    )

    tenant_b = create_test_tenant(
        code=f"TENANT-B-{uuid4().hex[:8].upper()}",
    )

    tenant_a_user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"config-a-{uuid4()}@example.com",
        tenant_id=tenant_a.id,
    )

    tenant_b_user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"config-b-{uuid4()}@example.com",
        tenant_id=tenant_b.id,
    )

    payload = {
        "key": "sla.test.config",
        "value": {
            "default_due_days": 24,
        },
        "category": "SLA",
        "status": "ACTIVE",
    }

    authenticate_client(
        client,
        tenant_a_user,
    )

    response_a = client.post(
        "/api/v1/system-configurations",
        json=payload,
    )

    assert response_a.status_code == 201

    authenticate_client(
        client,
        tenant_b_user,
    )

    response_b = client.post(
        "/api/v1/system-configurations",
        json=payload,
    )

    assert response_b.status_code == 201


def test_report_export_history_is_isolated_by_tenant(
    client,
    create_test_tenant,
    create_test_user,
    create_test_customer,
    cleanup_test_customers,
    cleanup_report_exports,
):
    tenant_a = create_test_tenant(
        code=f"TENANT-A-{uuid4().hex[:8].upper()}",
    )

    tenant_b = create_test_tenant(
        code=f"TENANT-B-{uuid4().hex[:8].upper()}",
    )

    tenant_a_user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"report-a-{uuid4()}@example.com",
        tenant_id=tenant_a.id,
    )

    tenant_b_user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"report-b-{uuid4()}@example.com",
        tenant_id=tenant_b.id,
    )

    create_test_customer(
        tenant_id=tenant_a.id,
        email=f"report-a-customer-{uuid4()}@example.com",
    )

    authenticate_client(
        client,
        tenant_a_user,
    )

    response = client.post(
        "/api/v1/reports/exports",
        json={
            "report_type": "CUSTOMER",
            "format": "CSV",
            "filters": {},
            "prefer_async": False,
        },
    )

    assert response.status_code == 201

    export_id = response.json()["data"]["id"]

    authenticate_client(
        client,
        tenant_b_user,
    )

    history_response = client.get(
        "/api/v1/reports/exports",
    )

    assert history_response.status_code == 200

    export_ids = {item["id"] for item in history_response.json()["data"]["exports"]}

    assert export_id not in export_ids
