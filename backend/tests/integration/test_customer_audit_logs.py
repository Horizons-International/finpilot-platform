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


def test_customer_update_creates_audit_history(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="audit-test@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, user)

    create_response = client.post(
        "/api/v1/customers",
        json={
            "first_name": "Audit",
            "last_name": "Customer",
            "email": "audit@example.com",
            "phone_number": "+249912345678",
        },
    )

    assert create_response.status_code == 201

    customer = create_response.json()["data"]
    customer_id = customer["id"]

    update_response = client.put(
        f"/api/v1/customers/{customer_id}",
        json={
            "first_name": "Updated",
            "email": "updated@example.com",
        },
    )

    assert update_response.status_code == 200

    history_response = client.get(
        f"/api/v1/customers/{customer_id}/audit-history",
    )

    assert history_response.status_code == 200

    body = history_response.json()

    assert body["success"] is True
    assert body["message"] == ("Customer audit history retrieved successfully.")

    audit_logs = body["data"]["audit_logs"]

    assert len(audit_logs) == 3

    fields = {audit["action"] for audit in audit_logs}

    assert fields == {"CREATE CUSTOMER", "UPDATE FIRST NAME", "UPDATE EMAIL"}

    for audit in audit_logs:
        assert audit["customer_id"] == customer_id
        assert audit["user_id"] == str(user.id)


def test_customer_audit_history_contains_old_and_new_values(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="audit-values@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, user)

    create_response = client.post(
        "/api/v1/customers",
        json={
            "first_name": "Original",
            "last_name": "Customer",
            "email": "original@example.com",
            "phone_number": "+249912345678",
        },
    )

    assert create_response.status_code == 201

    customer_id = create_response.json()["data"]["id"]

    update_response = client.put(
        f"/api/v1/customers/{customer_id}",
        json={
            "email": "changed@example.com",
        },
    )

    assert update_response.status_code == 200

    history_response = client.get(
        f"/api/v1/customers/{customer_id}/audit-history",
    )

    assert history_response.status_code == 200

    audit_logs = history_response.json()["data"]["audit_logs"]

    email_audit = next(
        audit for audit in audit_logs if audit["action"] == "UPDATE EMAIL"
    )

    assert email_audit["old_value"] == "original@example.com"
    assert email_audit["new_value"] == "changed@example.com"
    assert email_audit["user_id"] == str(user.id)


def test_customer_audit_history_records_nullable_field_clearing(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="audit-null@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, user)

    create_response = client.post(
        "/api/v1/customers",
        json={
            "first_name": "Audit",
            "middle_name": "Middle",
            "last_name": "Customer",
            "email": "audit-null@example.com",
            "phone_number": "+249912345678",
        },
    )

    assert create_response.status_code == 201

    customer_id = create_response.json()["data"]["id"]

    update_response = client.put(
        f"/api/v1/customers/{customer_id}",
        json={
            "middle_name": None,
        },
    )

    assert update_response.status_code == 200

    history_response = client.get(
        f"/api/v1/customers/{customer_id}/audit-history",
    )

    assert history_response.status_code == 200

    audit_logs = history_response.json()["data"]["audit_logs"]

    middle_name_audit = next(
        audit for audit in audit_logs if audit["action"] == "UPDATE MIDDLE NAME"
    )

    assert middle_name_audit["old_value"] == "Middle"
    assert middle_name_audit["new_value"] is None


def test_customer_audit_history_does_not_record_unchanged_fields(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="audit-unchanged@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, user)

    create_response = client.post(
        "/api/v1/customers",
        json={
            "first_name": "Same",
            "last_name": "Customer",
            "email": "same@example.com",
            "phone_number": "+249912345678",
        },
    )

    assert create_response.status_code == 201

    customer_id = create_response.json()["data"]["id"]

    update_response = client.put(
        f"/api/v1/customers/{customer_id}",
        json={
            "first_name": "Same",
            "email": "same@example.com",
        },
    )

    assert update_response.status_code == 400

    history_response = client.get(
        f"/api/v1/customers/{customer_id}/audit-history",
    )

    assert history_response.status_code == 200

    audit_logs = history_response.json()["data"]["audit_logs"]

    assert len(audit_logs) == 1


def test_customer_audit_history_is_newest_first(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="audit-order@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, user)

    create_response = client.post(
        "/api/v1/customers",
        json={
            "first_name": "First",
            "last_name": "Customer",
            "email": "first@example.com",
            "phone_number": "+249912345678",
        },
    )

    assert create_response.status_code == 201

    customer_id = create_response.json()["data"]["id"]

    first_update = client.put(
        f"/api/v1/customers/{customer_id}",
        json={
            "first_name": "Second",
        },
    )

    assert first_update.status_code == 200

    second_update = client.put(
        f"/api/v1/customers/{customer_id}",
        json={
            "first_name": "Third",
        },
    )

    assert second_update.status_code == 200

    history_response = client.get(
        f"/api/v1/customers/{customer_id}/audit-history",
    )

    assert history_response.status_code == 200

    audit_logs = history_response.json()["data"]["audit_logs"]

    assert len(audit_logs) == 3

    assert audit_logs[0]["old_value"] == "Second"
    assert audit_logs[0]["new_value"] == "Third"

    assert audit_logs[1]["old_value"] == "First"
    assert audit_logs[1]["new_value"] == "Second"


def test_customer_audit_history_customer_not_found(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="audit-not-found@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, user)

    customer_id = "00000000-0000-0000-0000-000000000000"

    response = client.get(
        f"/api/v1/customers/{customer_id}/audit-history",
    )

    assert response.status_code == 404


def test_customer_audit_history_requires_authorization(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="audit-owner@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    create_response = client.post(
        "/api/v1/customers",
        json={
            "first_name": "Audit",
            "last_name": "Customer",
            "email": "audit-owner@example.com",
            "phone_number": "+249912345678",
        },
    )

    assert create_response.status_code == 201

    customer_id = create_response.json()["data"]["id"]

    client.headers.clear()

    _, auditor = create_test_user(
        email="audit-reader@example.com",
        role=UserRole.AUDITOR,
    )

    authenticate_client(client, auditor)

    response = client.get(
        f"/api/v1/customers/{customer_id}/audit-history",
    )

    assert response.status_code == 403
