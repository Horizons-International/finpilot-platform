"""Integration coverage for the native-async operations dashboard route."""

from uuid import uuid4

from app.utils.enums import CustomerStatus, UserRole
from tests.helpers import authenticate_client


def test_operations_dashboard_is_tenant_scoped(
    client,
    create_test_tenant,
    create_test_user,
    create_test_customer,
):
    tenant_a = create_test_tenant(
        name=f"Dashboard tenant A {uuid4()}",
        code=f"DASH-A-{uuid4().hex[:10].upper()}",
    )
    tenant_b = create_test_tenant(
        name=f"Dashboard tenant B {uuid4()}",
        code=f"DASH-B-{uuid4().hex[:10].upper()}",
    )
    admin_a = create_test_user(
        UserRole.ADMINISTRATOR,
        f"dashboard-a-{uuid4()}@example.com",
        tenant_id=tenant_a.id,
    )
    create_test_customer(
        tenant_id=tenant_a.id,
        country_of_residence="Sudan",
        status=CustomerStatus.NEW,
    )
    create_test_customer(
        tenant_id=tenant_b.id,
        country_of_residence="Sudan",
        status=CustomerStatus.NEW,
    )

    authenticate_client(client, admin_a)
    response = client.get("/api/v1/dashboard/operations")

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["customers"]["total_customers"] == 1
    assert data["customers"]["new_registrations"] == 1


def test_operations_dashboard_rejects_invalid_date_range_async_route(
    client,
    create_test_user,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        f"dashboard-dates-{uuid4()}@example.com",
    )
    authenticate_client(client, admin)

    response = client.get(
        "/api/v1/dashboard/operations",
        params={"start_date": "2026-11-10", "end_date": "2026-11-01"},
    )

    assert response.status_code == 400
