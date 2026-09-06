from app.utils.enums import UserRole


def authenticate_client(client, user):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": user.email,
            "password": "Password123!",
        },
    )

    assert response.status_code == 200

    token = response.json()["data"]["access_token"]

    client.headers.update(
        {
            "Authorization": f"Bearer {token}",
        }
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


def initiate_verification(client, customer_id, verification_type="IDENTITY"):
    return client.post(
        f"/api/v1/customers/{customer_id}/verification",
        json={
            "verification_type": verification_type,
        },
    )


def test_verification_can_be_initiated(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="initiation-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="initiation-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = initiate_verification(
        client,
        customer_id,
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["customer_id"] == customer_id
    assert data["verification_type"] == "IDENTITY"
    assert data["status"] == "PENDING"
    assert data["assigned_to"] is None
    assert data["completed_at"] is None


def test_duplicate_active_verification_is_rejected(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="duplicate-initiation-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="duplicate-initiation-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    first_response = initiate_verification(
        client,
        customer_id,
    )

    assert first_response.status_code == 201

    second_response = initiate_verification(
        client,
        customer_id,
    )

    assert second_response.status_code == 400

    data = second_response.json()

    assert data["success"] is False


def test_duplicate_verification_is_rejected_while_under_review(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="under-review-duplicate-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="under-review-duplicate-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    first_response = initiate_verification(
        client,
        customer_id,
    )

    assert first_response.status_code == 201

    case_id = first_response.json()["data"]["id"]

    under_review_response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/status",
        json={
            "status": "UNDER_REVIEW",
        },
    )

    assert under_review_response.status_code == 200

    second_response = initiate_verification(
        client,
        customer_id,
    )

    assert second_response.status_code == 400

    data = second_response.json()

    assert data["success"] is False


def test_new_verification_can_be_initiated_after_previous_case_is_approved(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="reverification-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="reverification-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    first_response = initiate_verification(
        client,
        customer_id,
    )

    assert first_response.status_code == 201

    first_case_id = first_response.json()["data"]["id"]

    under_review_response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{first_case_id}/status",
        json={
            "status": "UNDER_REVIEW",
        },
    )

    assert under_review_response.status_code == 200

    approved_response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{first_case_id}/status",
        json={
            "status": "APPROVED",
        },
    )

    assert approved_response.status_code == 200

    second_response = initiate_verification(
        client,
        customer_id,
    )

    assert second_response.status_code == 201

    second_data = second_response.json()["data"]

    assert second_data["customer_id"] == customer_id
    assert second_data["verification_type"] == "IDENTITY"
    assert second_data["status"] == "PENDING"
    assert second_data["id"] != first_case_id
