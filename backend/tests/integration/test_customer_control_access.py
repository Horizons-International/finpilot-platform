from app.models.audit_log import AuditLog
from app.models.user import UserRole
from app.utils.enums import AuditEventType


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


def test_administrator_can_access_customer(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="admin-access@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, user)

    create_response = client.post(
        "/api/v1/customers",
        json={
            "first_name": "Admin",
            "last_name": "Customer",
            "email": "admin-customer@example.com",
            "phone_number": "+249912345678",
        },
    )

    assert create_response.status_code == 201

    customer_id = create_response.json()["data"]["id"]

    get_response = client.get(
        f"/api/v1/customers/{customer_id}",
    )

    assert get_response.status_code == 200

    body = get_response.json()

    assert body["success"] is True
    assert body["data"]["id"] == customer_id


def test_standard_user_cannot_create_customer(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, user = create_test_user(
        email="standard-customer-access@example.com",
        role=UserRole.AUDITOR,
    )

    authenticate_client(client, user)

    response = client.post(
        "/api/v1/customers",
        json={
            "first_name": "Standard",
            "last_name": "User",
            "email": "standard-customer@example.com",
            "phone_number": "+249912345678",
        },
    )

    assert response.status_code == 403

    body = response.json()

    assert body["message"] == ("You do not have permission to access this resource.")


def test_standard_user_cannot_view_customers(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="standard-view-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    create_response = client.post(
        "/api/v1/customers",
        json={
            "first_name": "Protected",
            "last_name": "Customer",
            "email": "protected@example.com",
            "phone_number": "+249912345678",
        },
    )

    assert create_response.status_code == 201

    customer_id = create_response.json()["data"]["id"]

    client.headers.clear()

    _, user = create_test_user(
        email="standard-view@example.com",
        role=UserRole.AUDITOR,
    )

    authenticate_client(client, user)

    response = client.get(
        f"/api/v1/customers/{customer_id}",
    )

    assert response.status_code == 403


def test_compliance_officer_can_view_customer(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="compliance-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    create_response = client.post(
        "/api/v1/customers",
        json={
            "first_name": "Compliance",
            "last_name": "Customer",
            "email": "compliance-customer@example.com",
            "phone_number": "+249912345678",
        },
    )

    assert create_response.status_code == 201

    customer_id = create_response.json()["data"]["id"]

    client.headers.clear()

    _, compliance_user = create_test_user(
        email="compliance-view@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(client, compliance_user)

    response = client.get(
        f"/api/v1/customers/{customer_id}",
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["data"]["id"] == customer_id


def test_reviewer_can_view_customer(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="reviewer-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    create_response = client.post(
        "/api/v1/customers",
        json={
            "first_name": "Reviewer",
            "last_name": "Customer",
            "email": "reviewer-customer@example.com",
            "phone_number": "+249912345678",
        },
    )

    assert create_response.status_code == 201

    customer_id = create_response.json()["data"]["id"]

    client.headers.clear()

    _, reviewer = create_test_user(
        email="reviewer-view@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, reviewer)

    response = client.get(
        f"/api/v1/customers/{customer_id}",
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["data"]["id"] == customer_id


def test_compliance_officer_cannot_create_customer(
    client,
    create_test_user,
):
    _, user = create_test_user(
        email="compliance-create@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(client, user)

    response = client.post(
        "/api/v1/customers",
        json={
            "first_name": "Compliance",
            "last_name": "Create",
            "email": "compliance-create-customer@example.com",
            "phone_number": "+249912345678",
        },
    )

    assert response.status_code == 403


def test_reviewer_cannot_create_customer(
    client,
    create_test_user,
):
    _, user = create_test_user(
        email="reviewer-create@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, user)

    response = client.post(
        "/api/v1/customers",
        json={
            "first_name": "Reviewer",
            "last_name": "Create",
            "email": "reviewer-create-customer@example.com",
            "phone_number": "+249912345678",
        },
    )

    assert response.status_code == 403


def test_standard_user_access_denial_is_audited(
    client,
    create_test_user,
    db_session,
):
    _, user = create_test_user(
        email="access-denied@example.com",
        role=UserRole.AUDITOR,
    )

    authenticate_client(client, user)

    response = client.get(
        "/api/v1/customers",
    )

    assert response.status_code == 403

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == user.id,
            AuditLog.event_type == AuditEventType.ACCESS_DENIED,
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )

    assert audit_log is not None
    assert audit_log.user_id == user.id
    assert audit_log.email == user.email
    assert audit_log.event_type == AuditEventType.ACCESS_DENIED
    assert audit_log.resource_type == "customer"
    assert audit_log.resource_id is None


def test_standard_user_customer_access_denial_records_resource_id(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
):
    _, admin = create_test_user(
        email="resource-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    create_response = client.post(
        "/api/v1/customers",
        json={
            "first_name": "Protected",
            "last_name": "Resource",
            "email": "protected-resource@example.com",
            "phone_number": "+249912345678",
        },
    )

    assert create_response.status_code == 201

    customer_id = create_response.json()["data"]["id"]

    client.headers.clear()

    _, user = create_test_user(
        email="resource-denied@example.com",
        role=UserRole.AUDITOR,
    )

    authenticate_client(client, user)

    response = client.get(
        f"/api/v1/customers/{customer_id}",
    )

    assert response.status_code == 403

    from app.models.audit_log import AuditLog
    from app.utils.enums import AuditEventType

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == user.id,
            AuditLog.event_type == AuditEventType.ACCESS_DENIED,
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )

    assert audit_log is not None
    assert audit_log.user_id == user.id
    assert audit_log.email == user.email
    assert audit_log.event_type == AuditEventType.ACCESS_DENIED
    assert audit_log.resource_type == "customer"
    assert str(audit_log.resource_id) == customer_id


def test_administrator_access_does_not_create_access_denied_audit(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
):
    _, user = create_test_user(
        email="admin-no-denied@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, user)

    response = client.get(
        "/api/v1/customers",
    )

    assert response.status_code == 200

    from app.models.audit_log import AuditLog
    from app.utils.enums import AuditEventType

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == user.id,
            AuditLog.event_type == AuditEventType.ACCESS_DENIED,
        )
        .first()
    )

    assert audit_log is None
