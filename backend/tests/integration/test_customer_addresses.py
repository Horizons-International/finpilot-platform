from uuid import UUID

from app.models.user import UserRole


def authenticate_client(client, user):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": user.email,
            "password": "Password123!",
        },
    )

    assert response.status_code == 200

    access_token = response.json()["data"]["access_token"]

    client.headers.update(
        {"Authorization": f"Bearer {access_token}"},
    )


def create_customer(client):
    return client.post(
        "/api/v1/customers",
        json={
            "first_name": "John",
            "middle_name": "Michael",
            "last_name": "Smith",
            "date_of_birth": "1990-05-15",
            "nationality": "US",
            "country_of_residence": "US",
            "email": "address.customer@example.com",
            "phone_number": "+249912345678",
            "status": "new",
        },
    )


def create_customer_with_data(client, **overrides):
    data = {
        "first_name": "John",
        "middle_name": "Michael",
        "last_name": "Smith",
        "date_of_birth": "1990-05-15",
        "nationality": "US",
        "country_of_residence": "US",
        "email": "john.smith@example.com",
        "phone_number": "+249912345678",
        "status": "new",
    }

    data.update(overrides)

    return client.post(
        "/api/v1/customers",
        json=data,
    )


def create_address(client, customer_id, **overrides):
    data = {
        "address_line_1": "123 Main Street",
        "address_line_2": "Apartment 4",
        "city": "New York",
        "state": "NY",
        "country": "US",
        "postal_code": "10001",
        "address_type": "residential",
        "is_primary": False,
    }

    data.update(overrides)

    return client.post(
        f"/api/v1/customers/{customer_id}/addresses",
        json=data,
    )


def test_create_customer_address(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="address-create@example.com",
    )

    authenticate_client(client, user)

    customer_response = create_customer(client)

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = create_address(
        client,
        customer_id,
        is_primary=True,
    )

    assert response.status_code == 201

    body = response.json()

    assert body["success"] is True
    assert body["message"] == "Customer address created successfully."

    address = body["data"]

    assert UUID(address["id"])
    assert address["customer_id"] == customer_id
    assert address["address_line_1"] == "123 Main Street"
    assert address["address_line_2"] == "Apartment 4"
    assert address["city"] == "New York"
    assert address["state"] == "NY"
    assert address["country"] == "US"
    assert address["postal_code"] == "10001"
    assert address["address_type"] == "residential"
    assert address["is_primary"] is True


def test_get_customer_addresses(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="address-get@example.com",
    )

    authenticate_client(client, user)

    customer_response = create_customer(client)

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    first_address_response = create_address(
        client,
        customer_id,
        address_line_1="123 First Street",
        city="New York",
        is_primary=True,
    )

    assert first_address_response.status_code == 201

    second_address_response = create_address(
        client,
        customer_id,
        address_line_1="456 Second Street",
        city="Boston",
        address_type="mailing",
    )

    assert second_address_response.status_code == 201

    response = client.get(
        f"/api/v1/customers/{customer_id}/addresses",
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["message"] == "Customer addresses retrieved successfully."

    addresses = body["data"]

    assert len(addresses) == 2

    assert addresses[0]["customer_id"] == customer_id
    assert addresses[1]["customer_id"] == customer_id


def test_update_customer_address(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="address-update@example.com",
    )

    authenticate_client(client, user)

    customer_response = create_customer(client)

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    create_response = create_address(
        client,
        customer_id,
    )

    assert create_response.status_code == 201

    address_id = create_response.json()["data"]["id"]

    response = client.put(
        f"/api/v1/customers/{customer_id}/addresses/{address_id}",
        json={
            "address_line_1": "789 Updated Street",
            "city": "Chicago",
            "state": "IL",
            "postal_code": "60601",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["message"] == "Customer address updated successfully."

    address = body["data"]

    assert address["id"] == address_id
    assert address["customer_id"] == customer_id
    assert address["address_line_1"] == "789 Updated Street"
    assert address["city"] == "Chicago"
    assert address["state"] == "IL"
    assert address["postal_code"] == "60601"


def test_update_customer_address_preserves_unchanged_fields(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="address-partial-update@example.com",
    )

    authenticate_client(client, user)

    customer_response = create_customer(client)

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    create_response = create_address(
        client,
        customer_id,
    )

    assert create_response.status_code == 201

    address_id = create_response.json()["data"]["id"]

    response = client.put(
        f"/api/v1/customers/{customer_id}/addresses/{address_id}",
        json={
            "city": "Chicago",
        },
    )

    assert response.status_code == 200

    body = response.json()
    address = body["data"]

    assert address["address_line_1"] == "123 Main Street"
    assert address["address_line_2"] == "Apartment 4"
    assert address["city"] == "Chicago"
    assert address["state"] == "NY"
    assert address["country"] == "US"
    assert address["postal_code"] == "10001"
    assert address["address_type"] == "residential"
    assert address["is_primary"] is False


def test_set_customer_address_primary(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="address-primary@example.com",
    )

    authenticate_client(client, user)

    customer_response = create_customer(client)

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    first_response = create_address(
        client,
        customer_id,
        address_line_1="123 First Street",
        is_primary=True,
    )

    assert first_response.status_code == 201

    first_address_id = first_response.json()["data"]["id"]

    second_response = create_address(
        client,
        customer_id,
        address_line_1="456 Second Street",
        is_primary=False,
    )

    assert second_response.status_code == 201

    second_address_id = second_response.json()["data"]["id"]

    response = client.patch(
        f"/api/v1/customers/{customer_id}/addresses/{second_address_id}/primary",
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["message"] == ("Customer address marked as primary successfully.")

    address = body["data"]

    assert address["id"] == second_address_id
    assert address["is_primary"] is True

    addresses_response = client.get(
        f"/api/v1/customers/{customer_id}/addresses",
    )

    assert addresses_response.status_code == 200

    addresses = addresses_response.json()["data"]

    first_address = next(
        address for address in addresses if address["id"] == first_address_id
    )

    second_address = next(
        address for address in addresses if address["id"] == second_address_id
    )

    assert first_address["is_primary"] is False
    assert second_address["is_primary"] is True


def test_get_nonexistent_customer_address(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="address-not-found@example.com",
    )

    authenticate_client(client, user)

    customer_id = "00000000-0000-0000-0000-000000000000"

    response = client.get(
        f"/api/v1/customers/{customer_id}/addresses",
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["data"] == []


def test_customer_address_create_requires_authorization(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        role=UserRole.AUDITOR,
        email="address-create-unauthorized@example.com",
    )

    authenticate_client(client, user)

    customer_id = "00000000-0000-0000-0000-000000000000"

    response = create_address(
        client,
        customer_id,
    )

    assert response.status_code == 403


def test_customer_address_get_requires_authorization(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="address-get-owner@example.com",
    )

    authenticate_client(client, admin)

    customer_response = create_customer(client)

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    client.headers.clear()

    _, auditor = create_test_user(
        role=UserRole.AUDITOR,
        email="address-get-unauthorized@example.com",
    )

    authenticate_client(client, auditor)

    response = client.get(
        f"/api/v1/customers/{customer_id}/addresses",
    )

    assert response.status_code == 403


def test_customer_address_update_requires_authorization(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="address-update-owner@example.com",
    )

    authenticate_client(client, admin)

    customer_response = create_customer(client)

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    address_response = create_address(
        client,
        customer_id,
    )

    assert address_response.status_code == 201

    address_id = address_response.json()["data"]["id"]

    client.headers.clear()

    _, auditor = create_test_user(
        role=UserRole.AUDITOR,
        email="address-update-unauthorized@example.com",
    )

    authenticate_client(client, auditor)

    response = client.put(
        f"/api/v1/customers/{customer_id}/addresses/{address_id}",
        json={
            "city": "Unauthorized City",
        },
    )

    assert response.status_code == 403


def test_create_customer_address_missing_required_field(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="address.missing@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, user)

    customer_response = create_customer(client)
    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = client.post(
        f"/api/v1/customers/{customer_id}/addresses",
        json={
            "address_line_2": "Apartment 4",
            "city": "New York",
            "state": "NY",
            "country": "US",
            "postal_code": "10001",
            "address_type": "residential",
            "is_primary": False,
        },
    )

    assert response.status_code == 422


def test_create_customer_address_invalid_address_type(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="address.invalid.type@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, user)

    customer_response = create_customer(client)
    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = create_address(
        client,
        customer_id,
        address_type="invalid_type",
    )

    assert response.status_code == 422


def test_update_nonexistent_customer_address(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="address.update.missing@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, user)

    customer_response = create_customer(client)
    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    address_id = UUID("00000000-0000-0000-0000-000000000000")

    response = client.put(
        f"/api/v1/customers/{customer_id}/addresses/{address_id}",
        json={
            "city": "Boston",
        },
    )

    assert response.status_code == 404


def test_update_customer_address_belonging_to_another_customer(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="address.update.other@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, user)

    first_customer_response = create_customer(client)
    assert first_customer_response.status_code == 201

    first_customer_id = first_customer_response.json()["data"]["id"]

    second_customer_response = create_customer_with_data(
        client,
        email="another.customer@example.com",
    )
    assert second_customer_response.status_code == 201

    second_customer_id = second_customer_response.json()["data"]["id"]

    address_response = create_address(client, second_customer_id)
    assert address_response.status_code == 201

    address_id = address_response.json()["data"]["id"]

    response = client.put(
        f"/api/v1/customers/{first_customer_id}/addresses/{address_id}",
        json={
            "city": "Boston",
        },
    )

    assert response.status_code == 404


def test_set_nonexistent_customer_address_as_primary(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="address.primary.missing@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, user)

    customer_response = create_customer(client)
    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    address_id = UUID("00000000-0000-0000-0000-000000000000")

    response = client.patch(
        f"/api/v1/customers/{customer_id}/addresses/{address_id}/primary",
    )

    assert response.status_code == 404


def test_set_another_customers_address_as_primary(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="address.primary.other@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, user)

    first_customer_response = create_customer(client)
    assert first_customer_response.status_code == 201

    first_customer_id = first_customer_response.json()["data"]["id"]

    second_customer_response = create_customer_with_data(
        client,
        email="another.customer@example.com",
    )
    assert second_customer_response.status_code == 201

    second_customer_id = second_customer_response.json()["data"]["id"]

    address_response = create_address(client, second_customer_id)
    assert address_response.status_code == 201

    address_id = address_response.json()["data"]["id"]

    response = client.patch(
        f"/api/v1/customers/{first_customer_id}/addresses/{address_id}/primary",
    )

    assert response.status_code == 404


def test_create_second_primary_address_makes_first_address_non_primary(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="address.second.primary@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, user)

    customer_response = create_customer(client)
    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    first_address_response = create_address(
        client,
        customer_id,
        is_primary=True,
    )
    assert first_address_response.status_code == 201

    first_address_id = first_address_response.json()["data"]["id"]
    assert first_address_response.json()["data"]["is_primary"] is True

    second_address_response = create_address(
        client,
        customer_id,
        address_line_1="456 Second Street",
        is_primary=True,
    )
    assert second_address_response.status_code == 201

    second_address_id = second_address_response.json()["data"]["id"]
    assert second_address_response.json()["data"]["is_primary"] is True

    response = client.get(
        f"/api/v1/customers/{customer_id}/addresses",
    )

    assert response.status_code == 200

    addresses = response.json()["data"]

    first_address = next(
        address for address in addresses if address["id"] == first_address_id
    )
    second_address = next(
        address for address in addresses if address["id"] == second_address_id
    )

    assert first_address["is_primary"] is False
    assert second_address["is_primary"] is True


def test_mark_secondary_address_as_primary_makes_previous_primary_non_primary(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="address.change.primary@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, user)

    customer_response = create_customer(client)
    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    first_address_response = create_address(
        client,
        customer_id,
        is_primary=True,
    )
    assert first_address_response.status_code == 201

    first_address_id = first_address_response.json()["data"]["id"]

    second_address_response = create_address(
        client,
        customer_id,
        address_line_1="456 Second Street",
        is_primary=False,
    )
    assert second_address_response.status_code == 201

    second_address_id = second_address_response.json()["data"]["id"]

    assert second_address_response.json()["data"]["is_primary"] is False

    response = client.patch(
        f"/api/v1/customers/{customer_id}/addresses/{second_address_id}/primary",
    )

    assert response.status_code == 200
    assert response.json()["data"]["id"] == second_address_id
    assert response.json()["data"]["is_primary"] is True

    response = client.get(
        f"/api/v1/customers/{customer_id}/addresses",
    )

    assert response.status_code == 200

    addresses = response.json()["data"]

    first_address = next(
        address for address in addresses if address["id"] == first_address_id
    )
    second_address = next(
        address for address in addresses if address["id"] == second_address_id
    )

    assert first_address["is_primary"] is False
    assert second_address["is_primary"] is True


def test_customer_can_have_multiple_non_primary_addresses(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="address.multiple.nonprimary@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, user)

    customer_response = create_customer(client)
    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    first_address_response = create_address(
        client,
        customer_id,
        is_primary=False,
    )
    assert first_address_response.status_code == 201
    assert first_address_response.json()["data"]["is_primary"] is False

    second_address_response = create_address(
        client,
        customer_id,
        address_line_1="456 Second Street",
        is_primary=False,
    )
    assert second_address_response.status_code == 201
    assert second_address_response.json()["data"]["is_primary"] is False

    response = client.get(
        f"/api/v1/customers/{customer_id}/addresses",
    )

    assert response.status_code == 200

    addresses = response.json()["data"]

    assert len(addresses) == 2
    assert all(address["is_primary"] is False for address in addresses)


def test_update_customer_address_all_fields(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="address.update.all@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, user)

    customer_response = create_customer(client)
    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    address_response = create_address(client, customer_id)
    assert address_response.status_code == 201

    address_id = address_response.json()["data"]["id"]

    response = client.put(
        f"/api/v1/customers/{customer_id}/addresses/{address_id}",
        json={
            "address_line_1": "789 Updated Avenue",
            "address_line_2": "Suite 10",
            "city": "Boston",
            "state": "MA",
            "country": "CA",
            "postal_code": "02108",
            "address_type": "mailing",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["id"] == address_id
    assert data["customer_id"] == customer_id
    assert data["address_line_1"] == "789 Updated Avenue"
    assert data["address_line_2"] == "Suite 10"
    assert data["city"] == "Boston"
    assert data["state"] == "MA"
    assert data["country"] == "CA"
    assert data["postal_code"] == "02108"
    assert data["address_type"] == "mailing"
    assert data["is_primary"] is False


def test_update_customer_address_type(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="address.update.type@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, user)

    customer_response = create_customer(client)
    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    address_response = create_address(
        client,
        customer_id,
        address_type="residential",
    )
    assert address_response.status_code == 201

    address_id = address_response.json()["data"]["id"]

    response = client.put(
        f"/api/v1/customers/{customer_id}/addresses/{address_id}",
        json={
            "address_type": "mailing",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["address_type"] == "mailing"
    assert data["address_line_1"] == "123 Main Street"
    assert data["city"] == "New York"
    assert data["country"] == "US"
    assert data["is_primary"] is False


def test_update_customer_address_sets_nullable_fields_to_null(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="address.update.nulls@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, user)

    customer_response = create_customer(client)
    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    address_response = create_address(
        client,
        customer_id,
        address_line_2="Apartment 4",
        state="NY",
        postal_code="10001",
    )
    assert address_response.status_code == 201

    address_id = address_response.json()["data"]["id"]

    response = client.put(
        f"/api/v1/customers/{customer_id}/addresses/{address_id}",
        json={
            "address_line_2": None,
            "state": None,
            "postal_code": None,
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["address_line_2"] is None
    assert data["state"] is None
    assert data["postal_code"] is None
    assert data["address_line_1"] == "123 Main Street"
    assert data["city"] == "New York"
    assert data["country"] == "US"
    assert data["address_type"] == "residential"
    assert data["is_primary"] is False


def test_create_customer_address_rejects_empty_required_fields(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="address.empty.required@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, user)

    customer_response = create_customer(client)
    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = create_address(
        client,
        customer_id,
        address_line_1="   ",
        city="New York",
        country="US",
    )

    assert response.status_code == 422


def test_create_customer_address_rejects_whitespace_only_city(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="address.whitespace.city@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, user)

    customer_response = create_customer(client)
    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = create_address(
        client,
        customer_id,
        address_line_1="123 Main Street",
        city="   ",
        country="US",
    )

    assert response.status_code == 422


def test_create_customer_address_rejects_whitespace_only_country(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="address.whitespace.country@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, user)

    customer_response = create_customer(client)
    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = create_address(
        client,
        customer_id,
        address_line_1="123 Main Street",
        city="New York",
        country="   ",
    )

    assert response.status_code == 422


def test_customer_address_set_primary_requires_authorization(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="address.primary.auth@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, user)

    customer_response = create_customer(client)
    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    address_response = create_address(
        client,
        customer_id,
    )
    assert address_response.status_code == 201

    address_id = address_response.json()["data"]["id"]

    client.headers.clear()

    response = client.patch(
        f"/api/v1/customers/{customer_id}/addresses/{address_id}/primary",
    )

    assert response.status_code == 401


def test_customer_address_sets_created_and_updated_timestamps(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="address.timestamps@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, user)

    customer_response = create_customer(client)
    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    address_response = create_address(
        client,
        customer_id,
    )
    assert address_response.status_code == 201

    data = address_response.json()["data"]

    assert data["created_at"] is not None
    assert data["updated_at"] is not None


def test_customer_address_updated_at_changes_on_update(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="address.updated.timestamp@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, user)

    customer_response = create_customer(client)
    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    address_response = create_address(
        client,
        customer_id,
    )
    assert address_response.status_code == 201

    address_data = address_response.json()["data"]
    address_id = address_data["id"]
    created_at = address_data["created_at"]
    updated_at = address_data["updated_at"]

    assert created_at is not None
    assert updated_at is not None

    response = client.put(
        f"/api/v1/customers/{customer_id}/addresses/{address_id}",
        json={
            "city": "Boston",
        },
    )

    assert response.status_code == 200

    updated_data = response.json()["data"]

    assert updated_data["created_at"] == created_at
    assert updated_data["updated_at"] is not None
