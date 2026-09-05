from app.models.audit_log import AuditLog
from app.utils.enums import AuditEventType, UserRole


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


def test_create_identity_verification_case(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="verification-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_reponse = create_customer_with_data(
        client,
        first_name="Verification",
        last_name="Customer",
        email="verification-customer@example.com",
    )

    customer_id = customer_reponse.json()["data"]["id"]

    response = client.post(
        f"/api/v1/customers/{customer_id}/verification-cases",
        json={
            "verification_type": "IDENTITY",
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["id"] is not None
    assert data["customer_id"] == str(customer_id)
    assert data["verification_type"] == "IDENTITY"
    assert data["status"] == "NOT_STARTED"
    assert data["assigned_to"] is None
    assert data["completed_at"] is None
    assert data["created_at"] is not None
    assert data["updated_at"] is not None


def test_create_address_verification_case(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="address-verification-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_reponse = create_customer_with_data(
        client,
        first_name="Address",
        last_name="Verification",
        email="address-verification@example.com",
    )

    customer_id = customer_reponse.json()["data"]["id"]

    response = client.post(
        f"/api/v1/customers/{customer_id}/verification-cases",
        json={
            "verification_type": "ADDRESS",
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["customer_id"] == str(customer_id)
    assert data["verification_type"] == "ADDRESS"
    assert data["status"] == "NOT_STARTED"


def test_get_customer_verification_cases(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="verification-list-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer = create_customer_with_data(
        client,
        first_name="Verification",
        last_name="List",
        email="verification-list@example.com",
    )

    customer_id = customer.json()["data"]["id"]

    first_response = client.post(
        f"/api/v1/customers/{customer_id}/verification-cases",
        json={
            "verification_type": "IDENTITY",
        },
    )

    assert first_response.status_code == 201

    second_response = client.post(
        f"/api/v1/customers/{customer_id}/verification-cases",
        json={
            "verification_type": "ADDRESS",
        },
    )

    assert second_response.status_code == 201

    response = client.get(
        f"/api/v1/customers/{customer_id}/verification-cases",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert len(data) == 2

    verification_types = {case["verification_type"] for case in data}

    assert verification_types == {
        "IDENTITY",
        "ADDRESS",
    }


def test_multiple_verification_cases_can_exist_for_customer(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="multiple-cases-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer = create_customer_with_data(
        client,
        first_name="Multiple",
        last_name="Cases",
        email="multiple-cases@example.com",
    )

    customer_id = customer.json()["data"]["id"]

    first_response = client.post(
        f"/api/v1/customers/{customer_id}/verification-cases",
        json={
            "verification_type": "IDENTITY",
        },
    )

    second_response = client.post(
        f"/api/v1/customers/{customer_id}/verification-cases",
        json={
            "verification_type": "ADDRESS",
        },
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201

    first_id = first_response.json()["data"]["id"]
    second_id = second_response.json()["data"]["id"]

    assert first_id != second_id


def test_create_verification_case_for_nonexistent_customer(
    client,
    create_test_user,
):
    _, admin = create_test_user(
        email="verification-not-found-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = client.post(
        "/api/v1/customers/00000000-0000-0000-0000-000000000000/verification-cases",
        json={
            "verification_type": "IDENTITY",
        },
    )

    assert response.status_code == 404


def test_compliance_officer_can_create_verification_case(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="verification-compliance-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        first_name="Compliance",
        last_name="Verification",
        email="compliance-verification@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    client.headers.clear()

    _, compliance_officer = create_test_user(
        email="verification-compliance@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(client, compliance_officer)

    response = client.post(
        f"/api/v1/customers/{customer_id}/verification-cases",
        json={
            "verification_type": "IDENTITY",
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["customer_id"] == customer_id
    assert data["verification_type"] == "IDENTITY"
    assert data["status"] == "NOT_STARTED"


def test_standard_user_cannot_view_verification_cases(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="verification-view-standard@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer = create_customer_with_data(
        client,
        first_name="Protected",
        last_name="Verification",
        email="protected-view@example.com",
    )

    customer_id = customer.json()["data"]["id"]

    assert customer.status_code == 201

    client.headers.clear()

    _, user = create_test_user(
        email="verification-reviewer@example.com",
        role=UserRole.AUDITOR,
    )

    authenticate_client(client, user)

    response = client.get(
        f"/api/v1/customers/{customer_id}/verification-cases",
    )

    assert response.status_code == 403


def test_reviewer_can_view_verification_cases(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="verification-review-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer = create_customer_with_data(
        client,
        first_name="Reviewer",
        last_name="Verification",
        email="reviewer-verification@example.com",
    )

    customer_id = customer.json()["data"]["id"]

    create_response = client.post(
        f"/api/v1/customers/{customer_id}/verification-cases",
        json={
            "verification_type": "IDENTITY",
        },
    )

    assert create_response.status_code == 201

    client.headers.clear()

    _, reviewer = create_test_user(
        email="verification-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, reviewer)

    response = client.get(
        f"/api/v1/customers/{customer_id}/verification-cases",
    )

    assert response.status_code == 200


def test_verification_case_creation_is_audited(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
):
    from app.models.audit_log import AuditLog
    from app.utils.enums import AuditEventType

    _, admin = create_test_user(
        email="verification-audit@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer = create_customer_with_data(
        client,
        first_name="Audit",
        last_name="Verification",
        email="audit-verification@example.com",
    )

    customer_id = customer.json()["data"]["id"]

    response = client.post(
        f"/api/v1/customers/{customer_id}/verification-cases",
        json={
            "verification_type": "IDENTITY",
        },
    )

    assert response.status_code == 201

    case_id = response.json()["data"]["id"]

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == admin.id,
            AuditLog.event_type == AuditEventType.VERIFICATION_CASE_CREATED,
            AuditLog.resource_type == "verification_case",
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )

    assert audit_log is not None
    assert audit_log.resource_id is not None
    assert str(audit_log.resource_id) == case_id


def create_verification_case(client, customer_id):
    response = client.post(
        f"/api/v1/customers/{customer_id}/verification-cases",
        json={
            "verification_type": "IDENTITY",
        },
    )

    assert response.status_code == 201

    return response.json()["data"]


def test_not_started_can_transition_to_pending(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="workflow-pending-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="workflow-pending-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    case = create_verification_case(client, customer_id)
    case_id = case["id"]

    response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/status",
        json={
            "status": "PENDING",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["id"] == case_id
    assert data["customer_id"] == customer_id
    assert data["status"] == "PENDING"
    assert data["completed_at"] is None


def test_pending_can_transition_to_under_review(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="workflow-review-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="workflow-review-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    case = create_verification_case(client, customer_id)
    case_id = case["id"]

    pending_response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/status",
        json={
            "status": "PENDING",
        },
    )

    assert pending_response.status_code == 200

    response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/status",
        json={
            "status": "UNDER_REVIEW",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["status"] == "UNDER_REVIEW"
    assert data["completed_at"] is None


def test_under_review_can_transition_to_approved(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="workflow-approved-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="workflow-approved-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    case = create_verification_case(client, customer_id)
    case_id = case["id"]

    client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/status",
        json={"status": "PENDING"},
    )

    client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/status",
        json={"status": "UNDER_REVIEW"},
    )

    response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/status",
        json={
            "status": "APPROVED",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["status"] == "APPROVED"
    assert data["completed_at"] is not None


def test_under_review_can_transition_to_rejected(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="workflow-rejected-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="workflow-rejected-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    case = create_verification_case(client, customer_id)
    case_id = case["id"]

    client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/status",
        json={"status": "PENDING"},
    )

    client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/status",
        json={"status": "UNDER_REVIEW"},
    )

    response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/status",
        json={
            "status": "REJECTED",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["status"] == "REJECTED"
    assert data["completed_at"] is not None


def test_invalid_verification_status_transition_is_rejected(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="workflow-invalid-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="workflow-invalid-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    case = create_verification_case(client, customer_id)
    case_id = case["id"]

    response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/status",
        json={
            "status": "APPROVED",
        },
    )

    assert response.status_code == 400

    data = response.json()

    assert data["success"] is False


def test_approved_cannot_transition_to_pending(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="workflow-terminal-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="workflow-terminal-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    case = create_verification_case(client, customer_id)
    case_id = case["id"]

    client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/status",
        json={"status": "PENDING"},
    )

    client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/status",
        json={"status": "UNDER_REVIEW"},
    )

    approved_response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/status",
        json={"status": "APPROVED"},
    )

    assert approved_response.status_code == 200

    response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/status",
        json={
            "status": "PENDING",
        },
    )

    assert response.status_code == 400


def test_invalid_transition_does_not_change_status(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="workflow-no-change-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="workflow-no-change-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    case = create_verification_case(client, customer_id)
    case_id = case["id"]

    pending_response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/status",
        json={"status": "PENDING"},
    )

    assert pending_response.status_code == 200

    response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/status",
        json={"status": "APPROVED"},
    )

    assert response.status_code == 400

    cases_response = client.get(
        f"/api/v1/customers/{customer_id}/verification-cases",
    )

    assert cases_response.status_code == 200

    cases = cases_response.json()["data"]

    updated_case = next(case for case in cases if case["id"] == case_id)

    assert updated_case["status"] == "PENDING"


def test_verification_status_change_is_audited(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
):
    _, admin = create_test_user(
        email="workflow-audit-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="workflow-audit-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    case = create_verification_case(client, customer_id)
    case_id = case["id"]

    response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/status",
        json={
            "status": "PENDING",
        },
    )

    assert response.status_code == 200

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == admin.id,
            AuditLog.event_type == AuditEventType.VERIFICATION_CASE_STATUS_CHANGED,
            AuditLog.resource_type == "verification_case",
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )

    assert audit_log is not None
    assert audit_log.resource_id is not None
    assert str(audit_log.resource_id) == case_id


def test_standard_user_cannot_update_verification_status(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="workflow-rbac-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="workflow-rbac-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    case = create_verification_case(client, customer_id)
    case_id = case["id"]

    client.headers.clear()

    _, user = create_test_user(
        email="workflow-rbac-user@example.com",
        role=UserRole.AUDITOR,
    )

    authenticate_client(client, user)

    response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/status",
        json={
            "status": "PENDING",
        },
    )

    assert response.status_code == 403


def test_update_nonexistent_verification_case_returns_404(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="workflow-not-found-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="workflow-not-found-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/"
        "00000000-0000-0000-0000-000000000000/status",
        json={
            "status": "PENDING",
        },
    )

    assert response.status_code == 404
