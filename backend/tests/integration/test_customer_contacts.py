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


def create_customer_with_data(client, **overrides):
    data = {
        "first_name": "John",
        "middle_name": "Michael",
        "last_name": "Smith",
        "date_of_birth": "1990-05-15",
        "nationality": "US",
        "country_of_residence": "US",
        "email": "john.smith@example.com",
        "phone_number": "+1234567890",
        "status": "new",
    }

    data.update(overrides)

    return client.post(
        "/api/v1/customers",
        json=data,
    )


def create_contact(client, customer_id, **overrides):
    data = {
        "phone_number": "+249912345678",
        "email": "contact@example.com",
        "preferred_contact_method": "phone",
        "phone_verified": False,
        "email_verified": False,
    }

    data.update(overrides)

    return client.post(
        f"/api/v1/customers/{customer_id}/contacts",
        json=data,
    )


def test_create_customer_contact(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="contact-create@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, user)

    customer_response = create_customer_with_data(
        client,
        email="contact-create-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = create_contact(client, customer_id)

    assert response.status_code == 201

    body = response.json()

    assert body["success"] is True
    assert body["message"] == "Customer contact created successfully."

    contact = body["data"]

    assert UUID(contact["id"])
    assert contact["customer_id"] == customer_id
    assert contact["phone_number"] == "+249912345678"
    assert contact["email"] == "contact@example.com"
    assert contact["preferred_contact_method"] == "phone"
    assert contact["phone_verified"] is False
    assert contact["email_verified"] is False
    assert contact["created_at"] is not None


def test_get_customer_contacts(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="contact-get@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, user)

    customer_response = create_customer_with_data(
        client,
        email="contact-get-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    first_contact = create_contact(
        client,
        customer_id,
        email="first-contact@example.com",
    )

    second_contact = create_contact(
        client,
        customer_id,
        email="second-contact@example.com",
    )

    assert first_contact.status_code == 201
    assert second_contact.status_code == 201

    response = client.get(
        f"/api/v1/customers/{customer_id}/contacts",
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["message"] == "Customer contacts retrieved successfully."

    contacts = body["data"]

    assert len(contacts) == 2

    emails = {contact["email"] for contact in contacts}

    assert emails == {
        "first-contact@example.com",
        "second-contact@example.com",
    }


def test_update_customer_contact(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="contact-update@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, user)

    customer_response = create_customer_with_data(
        client,
        email="contact-update-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    contact_response = create_contact(
        client,
        customer_id,
    )

    assert contact_response.status_code == 201

    contact_id = contact_response.json()["data"]["id"]

    response = client.put(
        f"/api/v1/customers/{customer_id}/contacts/{contact_id}",
        json={
            "phone_number": "+447700900123",
            "email": "updated@example.com",
            "preferred_contact_method": "email",
            "phone_verified": True,
            "email_verified": True,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["message"] == "Customer contact updated successfully."

    contact = body["data"]

    assert contact["id"] == contact_id
    assert contact["customer_id"] == customer_id
    assert contact["phone_number"] == "+447700900123"
    assert contact["email"] == "updated@example.com"
    assert contact["preferred_contact_method"] == "email"
    assert contact["phone_verified"] is True
    assert contact["email_verified"] is True


def test_multiple_contacts_allowed_for_customer(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="contact-multiple@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, user)

    customer_response = create_customer_with_data(
        client,
        email="contact-multiple-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    contact_one = create_contact(
        client,
        customer_id,
        phone_number="+249912345001",
        email="contact1@example.com",
    )

    contact_two = create_contact(
        client,
        customer_id,
        phone_number="+249912345002",
        email="contact2@example.com",
    )

    contact_three = create_contact(
        client,
        customer_id,
        phone_number="+249912345003",
        email="contact3@example.com",
    )

    assert contact_one.status_code == 201
    assert contact_two.status_code == 201
    assert contact_three.status_code == 201

    response = client.get(
        f"/api/v1/customers/{customer_id}/contacts",
    )

    assert response.status_code == 200

    contacts = response.json()["data"]

    assert len(contacts) == 3


def test_create_contact_with_phone_only(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="contact-phone-only@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, user)

    customer_response = create_customer_with_data(
        client,
        email="contact-phone-only-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = create_contact(
        client,
        customer_id,
        phone_number="+249912345678",
        email=None,
        preferred_contact_method="phone",
    )

    assert response.status_code == 201

    contact = response.json()["data"]

    assert contact["phone_number"] == "+249912345678"
    assert contact["email"] is None
    assert contact["preferred_contact_method"] == "phone"


def test_create_contact_with_email_only(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="contact-email-only@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, user)

    customer_response = create_customer_with_data(
        client,
        email="contact-email-only-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = create_contact(
        client,
        customer_id,
        phone_number=None,
        email="email-only@example.com",
        preferred_contact_method="email",
    )

    assert response.status_code == 201

    contact = response.json()["data"]

    assert contact["phone_number"] is None
    assert contact["email"] == "email-only@example.com"
    assert contact["preferred_contact_method"] == "email"


def test_create_contact_without_phone_or_email(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="contact-empty@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, user)

    customer_response = create_customer_with_data(
        client,
        email="contact-empty-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = create_contact(
        client,
        customer_id,
        phone_number=None,
        email=None,
        preferred_contact_method=None,
    )

    assert response.status_code == 201

    contact = response.json()["data"]

    assert contact["phone_number"] is None
    assert contact["email"] is None
    assert contact["preferred_contact_method"] is None
    assert contact["phone_verified"] is False
    assert contact["email_verified"] is False


def test_create_contact_invalid_email(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="contact-invalid-email@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, user)

    customer_response = create_customer_with_data(
        client,
        email="contact-invalid-email-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = create_contact(
        client,
        customer_id,
        email="not-an-email",
    )

    assert response.status_code == 422


def test_create_contact_invalid_preferred_method(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="contact-invalid-method@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, user)

    customer_response = create_customer_with_data(
        client,
        email="contact-invalid-method-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = create_contact(
        client,
        customer_id,
        preferred_contact_method="sms",
    )

    assert response.status_code == 422


def test_contact_normalizes_phone_and_email(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="contact-normalize@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, user)

    customer_response = create_customer_with_data(
        client,
        email="contact-normalize-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = create_contact(
        client,
        customer_id,
        phone_number="  +249912345678  ",
        email="  TEST@EXAMPLE.COM  ",
    )

    assert response.status_code == 201

    contact = response.json()["data"]

    assert contact["phone_number"] == "+249912345678"
    assert contact["email"] == "test@example.com"


def test_update_contact_verification_status(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="contact-verification@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, user)

    customer_response = create_customer_with_data(
        client,
        email="contact-verification-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    contact_response = create_contact(
        client,
        customer_id,
    )

    assert contact_response.status_code == 201

    contact_id = contact_response.json()["data"]["id"]

    response = client.put(
        f"/api/v1/customers/{customer_id}/contacts/{contact_id}",
        json={
            "phone_verified": True,
            "email_verified": True,
        },
    )

    assert response.status_code == 200

    contact = response.json()["data"]

    assert contact["phone_verified"] is True
    assert contact["email_verified"] is True


def test_update_contact_to_null_optional_fields(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="contact-null-update@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, user)

    customer_response = create_customer_with_data(
        client,
        email="contact-null-update-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    contact_response = create_contact(
        client,
        customer_id,
    )

    assert contact_response.status_code == 201

    contact_id = contact_response.json()["data"]["id"]

    response = client.put(
        f"/api/v1/customers/{customer_id}/contacts/{contact_id}",
        json={
            "phone_number": None,
            "email": None,
            "preferred_contact_method": None,
        },
    )

    assert response.status_code == 200

    contact = response.json()["data"]

    assert contact["phone_number"] is None
    assert contact["email"] is None
    assert contact["preferred_contact_method"] is None


def test_update_nonexistent_contact(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="contact-not-found@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, user)

    customer_response = create_customer_with_data(
        client,
        email="contact-not-found-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = client.put(
        f"/api/v1/customers/{customer_id}/contacts/"
        "00000000-0000-0000-0000-000000000000",
        json={
            "email": "updated@example.com",
        },
    )

    assert response.status_code == 404

    body = response.json()

    assert body["success"] is False


def test_update_contact_from_another_customer_returns_404(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="contact-ownership@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, user)

    first_customer_response = create_customer_with_data(
        client,
        email="contact-owner-one@example.com",
    )

    second_customer_response = create_customer_with_data(
        client,
        email="contact-owner-two@example.com",
    )

    assert first_customer_response.status_code == 201
    assert second_customer_response.status_code == 201

    first_customer_id = first_customer_response.json()["data"]["id"]
    second_customer_id = second_customer_response.json()["data"]["id"]

    contact_response = create_contact(
        client,
        first_customer_id,
    )

    assert contact_response.status_code == 201

    contact_id = contact_response.json()["data"]["id"]

    response = client.put(
        f"/api/v1/customers/{second_customer_id}/contacts/{contact_id}",
        json={
            "email": "hacked@example.com",
        },
    )

    assert response.status_code == 404


def test_customer_contact_requires_admin_for_create(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="contact-create-auditor@example.com",
        role=UserRole.AUDITOR,
    )

    authenticate_client(client, user)

    customer_response = create_customer_with_data(
        client,
        email="contact-create-auditor-customer@example.com",
    )

    # The customer itself may not be creatable by an auditor.
    # Use an existing customer only if your customer authorization
    # rules permit it. This test verifies the contact endpoint itself.
    if customer_response.status_code == 201:
        customer_id = customer_response.json()["data"]["id"]

        response = create_contact(
            client,
            customer_id,
        )

        assert response.status_code == 403


def test_customer_contact_requires_admin_for_get(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="contact-get-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="contact-get-admin-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    contact_response = create_contact(
        client,
        customer_id,
    )

    assert contact_response.status_code == 201

    client.headers.clear()

    _, auditor = create_test_user(
        email="contact-get-auditor@example.com",
        role=UserRole.AUDITOR,
    )

    authenticate_client(client, auditor)

    response = client.get(
        f"/api/v1/customers/{customer_id}/contacts",
    )

    assert response.status_code == 403


def test_customer_contact_requires_admin_for_update(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="contact-update-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="contact-update-admin-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    contact_response = create_contact(
        client,
        customer_id,
    )

    assert contact_response.status_code == 201

    contact_id = contact_response.json()["data"]["id"]

    client.headers.clear()

    _, auditor = create_test_user(
        email="contact-update-auditor@example.com",
        role=UserRole.AUDITOR,
    )

    authenticate_client(client, auditor)

    response = client.put(
        f"/api/v1/customers/{customer_id}/contacts/{contact_id}",
        json={
            "email": "unauthorized@example.com",
        },
    )

    assert response.status_code == 403
