from uuid import uuid4

from app.models.audit_log import AuditEventType, AuditLog
from app.models.verification_document_type import VerificationDocumentType
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

    client.headers.update({"Authorization": f"Bearer {token}"})


def test_initial_document_types_are_seeded(
    client,
    create_test_user,
):
    _, admin_user = create_test_user(
        email="initiation-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    response = client.get("/api/v1/verification-document-types")

    assert response.status_code == 200

    data = response.json()["data"]

    names = {item["name"] for item in data}

    assert "Passport" in names
    assert "National ID" in names
    assert "Driving License" in names
    assert "Proof of Address" in names


def test_create_document_type(
    client,
    create_test_user,
    reset_verification_document_types,
):
    _, admin_user = create_test_user(
        email="initiation-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    response = client.post(
        "/api/v1/verification-document-types",
        json={
            "name": "Residence Permit",
            "category": "IDENTITY",
            "supported_countries": ["SD", "GB"],
            "is_active": True,
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["name"] == "Residence Permit"
    assert data["category"] == "IDENTITY"
    assert data["supported_countries"] == ["SD", "GB"]
    assert data["is_active"] is True


def test_get_document_types(
    client,
    create_test_user,
):
    _, admin_user = create_test_user(
        email="initiation-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    response = client.get("/api/v1/verification-document-types")

    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


def test_get_active_document_types(
    client,
    create_test_user,
):
    _, admin_user = create_test_user(
        email="initiation-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    response = client.get("/api/v1/verification-document-types/active")

    assert response.status_code == 200

    for document_type in response.json()["data"]:
        assert document_type["is_active"] is True


def test_get_document_type_by_id(
    client,
    db_session,
    create_test_user,
):
    _, admin_user = create_test_user(
        email="initiation-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    document_type = db_session.query(VerificationDocumentType).first()

    response = client.get(f"/api/v1/verification-document-types/{document_type.id}")

    assert response.status_code == 200
    assert response.json()["data"]["id"] == str(document_type.id)


def test_get_nonexistent_document_type(
    client,
    create_test_user,
):
    _, admin_user = create_test_user(
        email="initiation-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    response = client.get(f"/api/v1/verification-document-types/{uuid4()}")

    assert response.status_code == 404


def test_deactivate_document_type(
    client,
    db_session,
    create_test_user,
    reset_verification_document_types,
):
    _, admin_user = create_test_user(
        email="initiation-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    document_type = db_session.query(VerificationDocumentType).first()

    response = client.patch(
        f"/api/v1/verification-document-types/{document_type.id}",
        json={
            "is_active": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["is_active"] is False


def test_reactivate_document_type(
    client,
    db_session,
    create_test_user,
):
    _, admin_user = create_test_user(
        email="initiation-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    document_type = db_session.query(VerificationDocumentType).first()

    response = client.patch(
        f"/api/v1/verification-document-types/{document_type.id}",
        json={
            "is_active": False,
        },
    )

    assert response.status_code == 200

    response = client.patch(
        f"/api/v1/verification-document-types/{document_type.id}",
        json={
            "is_active": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["is_active"] is True


def test_future_country_can_be_added(
    client,
    db_session,
    create_test_user,
    reset_verification_document_types,
):
    _, admin_user = create_test_user(
        email="initiation-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    document_type = db_session.query(VerificationDocumentType).first()

    response = client.patch(
        f"/api/v1/verification-document-types/{document_type.id}",
        json={
            "supported_countries": [
                "SD",
                "GB",
                "DE",
            ],
        },
    )

    assert response.status_code == 200

    assert response.json()["data"]["supported_countries"] == [
        "SD",
        "GB",
        "DE",
    ]


def test_duplicate_document_type_name_is_rejected(
    client,
    db_session,
    create_test_user,
):
    _, admin_user = create_test_user(
        email="initiation-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    existing = db_session.query(VerificationDocumentType).first()

    response = client.post(
        "/api/v1/verification-document-types",
        json={
            "name": existing.name,
            "category": "IDENTITY",
            "supported_countries": [],
            "is_active": True,
        },
    )

    assert response.status_code == 400


def test_invalid_country_code_is_rejected(
    client,
    create_test_user,
):
    _, admin_user = create_test_user(
        email="initiation-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    response = client.post(
        "/api/v1/verification-document-types",
        json={
            "name": "Test Document",
            "category": "IDENTITY",
            "supported_countries": ["USA"],
            "is_active": True,
        },
    )

    assert response.status_code == 422


def test_administrator_can_create_document_type(
    client,
    create_test_user,
    reset_verification_document_types,
):
    _, admin_user = create_test_user(
        email="initiation-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    response = client.post(
        "/api/v1/verification-document-types",
        json={
            "name": "Residence Permit",
            "category": "IDENTITY",
            "supported_countries": ["SD"],
            "is_active": True,
        },
    )

    assert response.status_code == 201


def test_compliance_officer_cannot_create_document_type(
    client,
    create_test_user,
):
    _, compliance_officer = create_test_user(
        email="initiation-admin@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(client, compliance_officer)

    response = client.post(
        "/api/v1/verification-document-types",
        json={
            "name": "Residence Permit",
            "category": "IDENTITY",
            "supported_countries": ["SD"],
            "is_active": True,
        },
    )

    assert response.status_code == 403


def test_reviewer_cannot_create_document_type(
    client,
    create_test_user,
):
    _, reviewer = create_test_user(
        email="initiation-admin@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, reviewer)

    response = client.post(
        "/api/v1/verification-document-types",
        json={
            "name": "Residence Permit",
            "category": "IDENTITY",
            "supported_countries": ["SD"],
            "is_active": True,
        },
    )

    assert response.status_code == 403


def test_standard_user_cannot_create_document_type(
    client,
    create_test_user,
):
    _, standard_user = create_test_user(
        email="initiation-admin@example.com",
        role=UserRole.AUDITOR,
    )

    authenticate_client(client, standard_user)

    response = client.post(
        "/api/v1/verification-document-types",
        json={
            "name": "Residence Permit",
            "category": "IDENTITY",
            "supported_countries": ["SD"],
            "is_active": True,
        },
    )

    assert response.status_code == 403


def test_compliance_officer_cannot_update_document_type(
    client,
    db_session,
    create_test_user,
):
    document_type = db_session.query(VerificationDocumentType).first()

    _, compliance_officer = create_test_user(
        email="initiation-admin@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(client, compliance_officer)

    response = client.patch(
        f"/api/v1/verification-document-types/{document_type.id}",
        json={
            "is_active": False,
        },
    )

    assert response.status_code == 403


def test_reviewer_cannot_update_document_type(
    client,
    db_session,
    create_test_user,
):
    _, reviewer = create_test_user(
        email="initiation-admin@example.com",
        role=UserRole.REVIEWER,
    )

    document_type = db_session.query(VerificationDocumentType).first()

    authenticate_client(client, reviewer)

    response = client.patch(
        f"/api/v1/verification-document-types/{document_type.id}",
        json={
            "is_active": False,
        },
    )

    assert response.status_code == 403


def test_standard_user_cannot_update_document_type(
    client,
    db_session,
    create_test_user,
):
    _, standard_user = create_test_user(
        email="initiation-admin@example.com",
        role=UserRole.AUDITOR,
    )

    document_type = db_session.query(VerificationDocumentType).first()

    authenticate_client(client, standard_user)

    response = client.patch(
        f"/api/v1/verification-document-types/{document_type.id}",
        json={
            "is_active": False,
        },
    )

    assert response.status_code == 403


def test_access_denied_is_audited_for_document_type_management(
    client,
    db_session,
    create_test_user,
):
    _, compliance_officer = create_test_user(
        email="initiation-admin@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(client, compliance_officer)

    response = client.post(
        "/api/v1/verification-document-types",
        json={
            "name": "Residence Permit",
            "category": "IDENTITY",
            "supported_countries": ["SD"],
            "is_active": True,
        },
    )

    assert response.status_code == 403

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.event_type == AuditEventType.ACCESS_DENIED,
            AuditLog.resource_type == "verification_document_type",
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )

    assert audit_log is not None


def test_document_type_creation_is_audited(
    client,
    db_session,
    create_test_user,
    reset_verification_document_types,
):
    _, admin_user = create_test_user(
        email="initiation-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    response = client.post(
        "/api/v1/verification-document-types",
        json={
            "name": "Residence Permit",
            "category": "IDENTITY",
            "supported_countries": ["SD"],
            "is_active": True,
        },
    )

    assert response.status_code == 201

    document_type_id = response.json()["data"]["id"]

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.event_type == AuditEventType.VERIFICATION_DOCUMENT_TYPE_CREATED,
            AuditLog.resource_type == "verification_document_type",
            AuditLog.resource_id == document_type_id,
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )

    assert audit_log is not None
    assert audit_log.user_id == admin_user.id
    assert audit_log.email == admin_user.email


def test_document_type_update_is_audited(
    client,
    db_session,
    create_test_user,
    reset_verification_document_types,
):
    _, admin_user = create_test_user(
        email="initiation-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    document_type = db_session.query(VerificationDocumentType).first()

    authenticate_client(client, admin_user)

    response = client.patch(
        f"/api/v1/verification-document-types/{document_type.id}",
        json={
            "supported_countries": ["SD", "GB"],
        },
    )

    assert response.status_code == 200

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.event_type == AuditEventType.VERIFICATION_DOCUMENT_TYPE_UPDATED,
            AuditLog.resource_type == "verification_document_type",
            AuditLog.resource_id == str(document_type.id),
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )

    assert audit_log is not None
    assert audit_log.user_id == admin_user.id
    assert audit_log.email == admin_user.email


def test_document_type_status_change_is_audited(
    client,
    db_session,
    create_test_user,
    reset_verification_document_types,
):
    _, admin_user = create_test_user(
        email="initiation-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    document_type = db_session.query(VerificationDocumentType).first()

    authenticate_client(client, admin_user)

    response = client.patch(
        f"/api/v1/verification-document-types/{document_type.id}",
        json={
            "is_active": False,
        },
    )

    assert response.status_code == 200

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.event_type
            == AuditEventType.VERIFICATION_DOCUMENT_TYPE_STATUS_CHANGED,
            AuditLog.resource_type == "verification_document_type",
            AuditLog.resource_id == str(document_type.id),
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )

    assert audit_log is not None
    assert audit_log.user_id == admin_user.id
    assert audit_log.email == admin_user.email


def test_document_type_country_update_is_not_status_change(
    client,
    db_session,
    create_test_user,
    reset_verification_document_types,
):
    _, admin_user = create_test_user(
        email="initiation-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    document_type = db_session.query(VerificationDocumentType).first()

    authenticate_client(client, admin_user)

    response = client.patch(
        f"/api/v1/verification-document-types/{document_type.id}",
        json={
            "supported_countries": ["SD", "GB", "DE"],
        },
    )

    assert response.status_code == 200

    updated_audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.event_type == AuditEventType.VERIFICATION_DOCUMENT_TYPE_UPDATED,
            AuditLog.resource_type == "verification_document_type",
            AuditLog.resource_id == str(document_type.id),
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )

    assert updated_audit is not None
