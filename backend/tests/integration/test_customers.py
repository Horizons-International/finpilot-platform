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
    assert customer["phone_number"] == "+249912345678"
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
            "phone_number": "+249912349999",
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
    assert customer["phone_number"] == "+249912349999"


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
    assert customer["phone_number"] == "+249912345678"
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


def test_search_customers_by_name(client, create_test_user, cleanup_test_customers):
    _, user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="customer-search-name@example.com",
    )

    authenticate_client(client, user)

    response = create_customer_with_data(
        client,
        first_name="Alice",
        last_name="Johnson",
        email="alice.johnson@example.com",
        phone_number="+249912341111",
    )

    assert response.status_code == 201

    customer = response.json()["data"]
    customer_id = customer["id"]

    response = client.get(
        "/api/v1/customers",
        params={"name": "Alice"},
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True

    customers = body["data"]["customers"]

    assert any(customer["id"] == customer_id for customer in customers)


def test_search_customers_by_email(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="customer-search-email@example.com",
    )

    authenticate_client(client, user)

    response = create_customer_with_data(
        client,
        email="search.email@example.com",
    )

    assert response.status_code == 201

    customer_id = response.json()["data"]["id"]

    response = client.get(
        "/api/v1/customers",
        params={
            "email": "search.email@example.com",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True

    customers = body["data"]["customers"]

    assert len(customers) == 1
    assert customers[0]["id"] == customer_id
    assert customers[0]["email"] == "search.email@example.com"


def test_search_customers_by_phone_number(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="customer-search-phone@example.com",
    )

    authenticate_client(client, user)

    response = create_customer_with_data(
        client,
        email="search.phone@example.com",
        phone_number="+249912347777",
    )

    assert response.status_code == 201

    customer_id = response.json()["data"]["id"]

    response = client.get(
        "/api/v1/customers",
        params={
            "phone_number": "+249912347777",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True

    customers = body["data"]["customers"]

    assert len(customers) == 1
    assert customers[0]["id"] == customer_id
    assert customers[0]["phone_number"] == "+249912347777"


def test_search_customers_by_id(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="customer-search-id@example.com",
    )

    authenticate_client(client, user)

    response = create_customer_with_data(
        client,
        email="search.id@example.com",
    )

    assert response.status_code == 201

    customer_id = response.json()["data"]["id"]

    response = client.get(
        "/api/v1/customers",
        params={
            "customer_id": customer_id,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True

    customers = body["data"]["customers"]

    assert len(customers) == 1
    assert customers[0]["id"] == customer_id


def test_search_customers_returns_empty_results(
    client,
    create_test_user,
):
    _, user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="customer-search-empty@example.com",
    )

    authenticate_client(client, user)

    response = client.get(
        "/api/v1/customers",
        params={
            "email": "does-not-exist@example.com",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["data"]["customers"] == []
    assert body["data"]["total"] == 0


def test_search_customers_pagination(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="customer-search-pagination@example.com",
    )

    authenticate_client(client, user)

    customer_ids = []

    first_names = [
        "PaginationAlice",
        "PaginationBob",
        "PaginationCharlie",
    ]

    for index, first_name in enumerate(first_names):
        response = create_customer_with_data(
            client,
            first_name=first_name,
            email=f"pagination{index}@example.com",
            phone_number=f"+24991234567{index}",
        )

        assert response.status_code == 201

        customer_ids.append(
            response.json()["data"]["id"],
        )

    response = client.get(
        "/api/v1/customers",
        params={
            "name": "Pagination",
            "page": 1,
            "page_size": 2,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["data"]["page"] == 1
    assert body["data"]["page_size"] == 2
    assert body["data"]["total"] == 3
    assert body["data"]["total_pages"] == 2
    assert len(body["data"]["customers"]) == 2

    response = client.get(
        "/api/v1/customers",
        params={
            "name": "Pagination",
            "page": 2,
            "page_size": 2,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["data"]["page"] == 2
    assert len(body["data"]["customers"]) == 1


def test_search_customers_by_status(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="customer-search-status@example.com",
    )

    authenticate_client(client, user)

    create_response = create_customer_with_data(
        client,
        email="search.status@example.com",
    )

    assert create_response.status_code == 201

    customer = create_response.json()["data"]
    customer_id = customer["id"]

    assert customer["status"] == "new"

    status_response = client.patch(
        f"/api/v1/customers/{customer_id}/status",
        json={"status": "pending_verification"},
    )

    assert status_response.status_code == 200

    status_body = status_response.json()

    assert status_body["success"] is True
    assert status_body["data"]["status"] == "pending_verification"

    response = client.get(
        "/api/v1/customers",
        params={
            "status": "pending_verification",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True

    customers = body["data"]["customers"]

    assert any(customer["id"] == customer_id for customer in customers)

    assert all(customer["status"] == "pending_verification" for customer in customers)


def test_search_customers_requires_authorization(
    client,
    create_test_user,
):
    _, user = create_test_user(
        role=UserRole.AUDITOR,
        email="customer-search-unauthorized@example.com",
    )

    authenticate_client(client, user)

    response = client.get(
        "/api/v1/customers",
    )

    assert response.status_code == 403
