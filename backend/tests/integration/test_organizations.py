from uuid import uuid4

from app.utils.enums import UserRole
from tests.helpers import authenticate_client


def test_administrator_can_create_organization(
    client,
    create_test_user,
    cleanup_organizations,
):
    admin = create_test_user(
        email=f"organization-admin-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.post(
        "/api/v1/organizations",
        json={
            "name": "FinPilot Bank",
            "legal_name": "FinPilot Bank Ltd.",
            "registration_number": "REG-12345",
            "tax_identification_number": "TAX-12345",
            "industry": "Financial Services",
            "business_description": "Commercial banking organization.",
            "contact_name": "John Smith",
            "contact_email": "contact@finpilot.example",
            "contact_phone": "+249912345678",
            "website": "https://finpilot.example",
            "country": "SD",
            "status": "ACTIVE",
            "settings": {
                "default_currency": "SDG",
                "timezone": "Africa/Khartoum",
            },
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["name"] == "FinPilot Bank"
    assert data["legal_name"] == "FinPilot Bank Ltd."
    assert data["country"] == "SD"
    assert data["status"] == "ACTIVE"
    assert data["settings"]["default_currency"] == "SDG"


def test_administrator_can_get_organization(
    client,
    create_test_user,
    cleanup_organizations,
):
    admin = create_test_user(
        email=f"organization-get-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    create_response = client.post(
        "/api/v1/organizations",
        json={
            "name": "FinPilot Bank",
            "country": "SD",
        },
    )

    assert create_response.status_code == 201

    organization_id = create_response.json()["data"]["id"]

    response = client.get(
        f"/api/v1/organizations/{organization_id}",
    )

    assert response.status_code == 200
    assert response.json()["data"]["id"] == organization_id


def test_administrator_can_update_organization(
    client,
    create_test_user,
    cleanup_organizations,
):
    admin = create_test_user(
        email=f"organization-update-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    create_response = client.post(
        "/api/v1/organizations",
        json={
            "name": "Old Organization Name",
            "country": "SD",
        },
    )

    assert create_response.status_code == 201

    organization_id = create_response.json()["data"]["id"]

    response = client.put(
        f"/api/v1/organizations/{organization_id}",
        json={
            "name": "New Organization Name",
            "industry": "Banking",
            "settings": {
                "default_currency": "SDG",
            },
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["name"] == "New Organization Name"
    assert data["industry"] == "Banking"
    assert data["settings"]["default_currency"] == "SDG"


def test_only_one_organization_can_exist_per_tenant(
    client,
    create_test_user,
    cleanup_organizations,
):
    admin = create_test_user(
        email=f"organization-duplicate-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    payload = {
        "name": "FinPilot Bank",
        "country": "SD",
    }

    first_response = client.post(
        "/api/v1/organizations",
        json=payload,
    )

    assert first_response.status_code == 201

    second_response = client.post(
        "/api/v1/organizations",
        json=payload,
    )

    assert second_response.status_code == 409


def test_non_administrator_cannot_manage_organization(
    client,
    create_test_user,
    cleanup_organizations,
):
    reviewer = create_test_user(
        email=f"organization-reviewer-{uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(
        client,
        reviewer,
    )

    response = client.post(
        "/api/v1/organizations",
        json={
            "name": "Unauthorized Organization",
            "country": "SD",
        },
    )

    assert response.status_code == 403


def test_organization_is_isolated_between_tenants(
    client,
    create_test_tenant,
    create_test_user,
    cleanup_organizations,
):
    tenant_a = create_test_tenant(
        code=f"ORGA-{uuid4().hex[:8].upper()}",
    )

    admin_a = create_test_user(
        email=f"organization-a-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
        tenant_id=tenant_a.id,
    )

    authenticate_client(
        client,
        admin_a,
    )

    create_response = client.post(
        "/api/v1/organizations",
        json={
            "name": "Tenant A Organization",
            "country": "SD",
        },
    )

    assert create_response.status_code == 201

    organization_id = create_response.json()["data"]["id"]

    tenant_b = create_test_tenant(
        code=f"ORGB-{uuid4().hex[:8].upper()}",
    )

    admin_b = create_test_user(
        email=f"organization-b-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
        tenant_id=tenant_b.id,
    )

    authenticate_client(
        client,
        admin_b,
    )

    response = client.get(
        f"/api/v1/organizations/{organization_id}",
    )

    assert response.status_code == 404
