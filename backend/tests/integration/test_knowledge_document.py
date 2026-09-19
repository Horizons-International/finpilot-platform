from app.models.audit_log import AuditLog
from app.utils.enums import AuditEventType, UserRole
from tests.helpers import authenticate_client


def test_create_knowledge_document(
    client,
    create_test_user,
    cleanup_test_files,
    cleanup_knowledge_documents,
):
    admin = create_test_user(
        email="knowledge-create-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = client.post(
        "/api/v1/knowledge-documents",
        data={
            "name": "AML Policy",
            "category": "COMPLIANCE_POLICY",
        },
        files={
            "file": (
                "aml-policy.pdf",
                b"AML policy content",
                "application/pdf",
            ),
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    cleanup_test_files(data["file_reference"])

    assert data["name"] == "AML Policy"
    assert data["category"] == "COMPLIANCE_POLICY"
    assert data["version"] == 1
    assert data["status"] == "INACTIVE"
    assert data["uploaded_by"] == str(admin.id)
    assert data["file_reference"]
    assert data["created_at"]


def test_create_knowledge_document_requires_administrator(
    client,
    create_test_user,
    cleanup_test_files,
    cleanup_knowledge_documents,
):
    user = create_test_user(
        email="knowledge-create-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, user)

    response = client.post(
        "/api/v1/knowledge-documents",
        data={
            "name": "AML Policy",
            "category": "COMPLIANCE_POLICY",
        },
        files={
            "file": (
                "aml-policy.pdf",
                b"AML policy content",
                "application/pdf",
            ),
        },
    )

    assert response.status_code == 403


def test_create_knowledge_document_version(
    client,
    create_test_user,
    cleanup_test_files,
    cleanup_knowledge_documents,
):
    admin = create_test_user(
        email="knowledge-version-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    create_response = client.post(
        "/api/v1/knowledge-documents",
        data={
            "name": "AML Policy",
            "category": "COMPLIANCE_POLICY",
        },
        files={
            "file": (
                "aml-policy-v1.pdf",
                b"AML policy version 1",
                "application/pdf",
            ),
        },
    )

    assert create_response.status_code == 201

    document_id = create_response.json()["data"]["id"]

    response = client.post(
        f"/api/v1/knowledge-documents/{document_id}/versions",
        files={
            "file": (
                "aml-policy-v2.pdf",
                b"AML policy version 2",
                "application/pdf",
            ),
        },
    )

    cleanup_test_files(create_response.json()["data"]["file_reference"])
    cleanup_test_files(response.json()["data"]["file_reference"])

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["name"] == "AML Policy"
    assert data["category"] == "COMPLIANCE_POLICY"
    assert data["version"] == 2
    assert data["status"] == "INACTIVE"


def test_list_knowledge_document_versions(
    client,
    create_test_user,
    cleanup_test_files,
    cleanup_knowledge_documents,
):
    admin = create_test_user(
        email="knowledge-list-version-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    create_response = client.post(
        "/api/v1/knowledge-documents",
        data={
            "name": "AML Policy",
            "category": "COMPLIANCE_POLICY",
        },
        files={
            "file": (
                "aml-policy-v1.pdf",
                b"version 1",
                "application/pdf",
            ),
        },
    )

    assert create_response.status_code == 201

    document_id = create_response.json()["data"]["id"]

    version_response = client.post(
        f"/api/v1/knowledge-documents/{document_id}/versions",
        files={
            "file": (
                "aml-policy-v2.pdf",
                b"version 2",
                "application/pdf",
            ),
        },
    )

    cleanup_test_files(create_response.json()["data"]["file_reference"])
    cleanup_test_files(version_response.json()["data"]["file_reference"])

    assert version_response.status_code == 201

    response = client.get(
        f"/api/v1/knowledge-documents/{document_id}/versions",
    )

    assert response.status_code == 200

    versions = response.json()["data"]

    assert len(versions) == 2
    assert versions[0]["version"] == 2
    assert versions[1]["version"] == 1


def test_activate_knowledge_document(
    client,
    create_test_user,
    cleanup_test_files,
    cleanup_knowledge_documents,
):
    admin = create_test_user(
        email="knowledge-activate-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    create_response = client.post(
        "/api/v1/knowledge-documents",
        data={
            "name": "AML Policy",
            "category": "COMPLIANCE_POLICY",
        },
        files={
            "file": (
                "aml-policy.pdf",
                b"AML policy",
                "application/pdf",
            ),
        },
    )

    assert create_response.status_code == 201

    document_id = create_response.json()["data"]["id"]

    cleanup_test_files(create_response.json()["data"]["file_reference"])

    response = client.patch(
        f"/api/v1/knowledge-documents/{document_id}/status",
        json={
            "status": "ACTIVE",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["status"] == "ACTIVE"


def test_deactivate_knowledge_document(
    client,
    create_test_user,
    cleanup_test_files,
    cleanup_knowledge_documents,
):
    admin = create_test_user(
        email="knowledge-deactivate-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    create_response = client.post(
        "/api/v1/knowledge-documents",
        data={
            "name": "AML Policy",
            "category": "COMPLIANCE_POLICY",
        },
        files={
            "file": (
                "aml-policy.pdf",
                b"AML policy",
                "application/pdf",
            ),
        },
    )

    document_id = create_response.json()["data"]["id"]

    cleanup_test_files(create_response.json()["data"]["file_reference"])

    activate_response = client.patch(
        f"/api/v1/knowledge-documents/{document_id}/status",
        json={
            "status": "ACTIVE",
        },
    )

    assert activate_response.status_code == 200

    response = client.patch(
        f"/api/v1/knowledge-documents/{document_id}/status",
        json={
            "status": "INACTIVE",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["status"] == "INACTIVE"


def test_only_one_active_version_per_document_name(
    client,
    create_test_user,
    cleanup_test_files,
    cleanup_knowledge_documents,
):
    admin = create_test_user(
        email="knowledge-single-active-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    create_response = client.post(
        "/api/v1/knowledge-documents",
        data={
            "name": "AML Policy",
            "category": "COMPLIANCE_POLICY",
        },
        files={
            "file": (
                "aml-policy-v1.pdf",
                b"version 1",
                "application/pdf",
            ),
        },
    )

    cleanup_test_files(create_response.json()["data"]["file_reference"])

    document_id = create_response.json()["data"]["id"]

    activate_response = client.patch(
        f"/api/v1/knowledge-documents/{document_id}/status",
        json={
            "status": "ACTIVE",
        },
    )

    assert activate_response.status_code == 200

    version_response = client.post(
        f"/api/v1/knowledge-documents/{document_id}/versions",
        files={
            "file": (
                "aml-policy-v2.pdf",
                b"version 2",
                "application/pdf",
            ),
        },
    )

    cleanup_test_files(version_response.json()["data"]["file_reference"])

    assert version_response.status_code == 201

    version_id = version_response.json()["data"]["id"]

    response = client.patch(
        f"/api/v1/knowledge-documents/{version_id}/status",
        json={
            "status": "ACTIVE",
        },
    )

    assert response.status_code == 400


def test_knowledge_document_creation_is_audited(
    client,
    create_test_user,
    cleanup_test_files,
    db_session,
    cleanup_knowledge_documents,
):
    admin = create_test_user(
        email="knowledge-audit-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = client.post(
        "/api/v1/knowledge-documents",
        data={
            "name": "AML Policy",
            "category": "COMPLIANCE_POLICY",
        },
        files={
            "file": (
                "aml-policy.pdf",
                b"AML policy",
                "application/pdf",
            ),
        },
    )

    assert response.status_code == 201

    cleanup_test_files(response.json()["data"]["file_reference"])

    document_id = response.json()["data"]["id"]

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == admin.id,
            AuditLog.event_type == AuditEventType.KNOWLEDGE_DOCUMENT_CREATED,
            AuditLog.resource_type == "knowledge_document",
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )

    assert audit_log is not None
    assert audit_log.resource_id is not None
    assert str(audit_log.resource_id) == document_id
