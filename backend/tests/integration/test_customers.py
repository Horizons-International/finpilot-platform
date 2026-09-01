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
            "email": "john.smith@example.com",
            "phone_number": "+1234567890",
            "status": "new",
        },
    )


def test_create_customer(client, create_test_user, cleanup_test_customers):
    _, user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="customer-create@example.com",
    )

    authenticate_client(client, user)

    response = create_customer(client)

    assert response.status_code == 201

    body = response.json()

    assert body["success"] is True
    assert body["message"] == "Customer created successfully."

    customer = body["data"]

    assert UUID(customer["id"])
    assert customer["first_name"] == "John"
    assert customer["middle_name"] == "Michael"
    assert customer["last_name"] == "Smith"
    assert customer["date_of_birth"] == "1990-05-15"
    assert customer["nationality"] == "US"
    assert customer["country_of_residence"] == "US"
    assert customer["email"] == "john.smith@example.com"
    assert customer["phone_number"] == "+1234567890"
    assert customer["status"] == "new"


def test_get_customer(client, create_test_user, cleanup_test_customers):
    _, user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="customer-get@example.com",
    )

    authenticate_client(client, user)

    create_response = create_customer(client)

    assert create_response.status_code == 201

    customer_id = create_response.json()["data"]["id"]

    response = client.get(
        f"/api/v1/customers/{customer_id}",
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["message"] == "Customer retrieved successfully."

    customer = body["data"]

    assert customer["id"] == customer_id
    assert customer["first_name"] == "John"
    assert customer["last_name"] == "Smith"
    assert customer["email"] == "john.smith@example.com"


def test_update_customer(client, create_test_user, cleanup_test_customers):
    _, user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="customer-update@example.com",
    )

    authenticate_client(client, user)

    create_response = create_customer(client)

    assert create_response.status_code == 201

    customer_id = create_response.json()["data"]["id"]

    response = client.put(
        f"/api/v1/customers/{customer_id}",
        json={
            "first_name": "Jonathan",
            "middle_name": "Michael",
            "last_name": "Smith",
            "date_of_birth": "1990-05-15",
            "nationality": "US",
            "country_of_residence": "US",
            "email": "johnathan.smith@example.com",
            "phone_number": "+1987654321",
            "status": "new",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["message"] == "Customer updated successfully."

    customer = body["data"]

    assert customer["id"] == customer_id
    assert customer["first_name"] == "Jonathan"
    assert customer["email"] == "johnathan.smith@example.com"
    assert customer["phone_number"] == "+1987654321"


def test_update_customer_preserves_unchanged_fields(
    client, create_test_user, cleanup_test_customers
):
    _, user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="customer-partial-update@example.com",
    )

    authenticate_client(client, user)

    create_response = create_customer(client)

    assert create_response.status_code == 201

    customer_id = create_response.json()["data"]["id"]

    response = client.put(
        f"/api/v1/customers/{customer_id}",
        json={
            "first_name": "Jonathan",
        },
    )

    assert response.status_code == 200

    body = response.json()
    customer = body["data"]

    assert customer["first_name"] == "Jonathan"
    assert customer["middle_name"] == "Michael"
    assert customer["last_name"] == "Smith"
    assert customer["date_of_birth"] == "1990-05-15"
    assert customer["nationality"] == "US"
    assert customer["country_of_residence"] == "US"
    assert customer["email"] == "john.smith@example.com"
    assert customer["phone_number"] == "+1234567890"
    assert customer["status"] == "new"


def test_get_nonexistent_customer(client, create_test_user, cleanup_test_customers):
    _, user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="customer-not-found@example.com",
    )

    authenticate_client(client, user)

    customer_id = "00000000-0000-0000-0000-000000000000"

    response = client.get(
        f"/api/v1/customers/{customer_id}",
    )

    assert response.status_code == 404

    body = response.json()

    assert body["success"] is False


def test_customer_create_requires_authorization(
    client, create_test_user, cleanup_test_customers
):
    _, user = create_test_user(
        role=UserRole.AUDITOR,
        email="customer-create-unauthorized@example.com",
    )

    authenticate_client(client, user)

    response = create_customer(client)

    assert response.status_code == 403


def test_customer_get_requires_authorization(
    client, create_test_user, cleanup_test_customers
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="customer-get-owner@example.com",
    )

    authenticate_client(client, admin)

    create_response = create_customer(client)

    assert create_response.status_code == 201

    customer_id = create_response.json()["data"]["id"]

    client.headers.clear()

    _, auditor = create_test_user(
        role=UserRole.AUDITOR,
        email="customer-get-unauthorized@example.com",
    )

    authenticate_client(client, auditor)

    response = client.get(
        f"/api/v1/customers/{customer_id}",
    )

    assert response.status_code == 403


def test_customer_update_requires_authorization(
    client, create_test_user, cleanup_test_customers
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="customer-update-owner@example.com",
    )

    authenticate_client(client, admin)

    create_response = create_customer(client)

    assert create_response.status_code == 201

    customer_id = create_response.json()["data"]["id"]

    client.headers.clear()

    _, auditor = create_test_user(
        role=UserRole.AUDITOR,
        email="customer-update-unauthorized@example.com",
    )

    authenticate_client(client, auditor)

    response = client.put(
        f"/api/v1/customers/{customer_id}",
        json={
            "first_name": "Unauthorized",
        },
    )

    assert response.status_code == 403


def test_create_customer_validates_required_fields(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="customer-validation@example.com",
    )

    authenticate_client(client, user)

    response = client.post(
        "/api/v1/customers",
        json={
            "first_name": "",
            "last_name": "Smith",
            "email": "invalid-email",
        },
    )

    assert response.status_code == 422
