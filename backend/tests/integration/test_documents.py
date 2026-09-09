from io import BytesIO
from uuid import UUID

from app.models.document import CustomerDocument
from app.models.file import File
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


def create_verification_case(client, customer_id):
    return client.post(
        f"/api/v1/customers/{customer_id}/verification-cases",
        json={
            "verification_type": "IDENTITY",
        },
    )


def get_passport_document_type(db_session):
    document_type = (
        db_session.query(VerificationDocumentType)
        .filter(
            VerificationDocumentType.name == "Passport",
            VerificationDocumentType.is_active.is_(True),
        )
        .first()
    )

    assert document_type is not None

    return document_type


def upload_document(
    client,
    customer_id,
    verification_case_id,
    document_type_id,
    filename="passport.pdf",
    content_type="application/pdf",
    content=b"%PDF-1.4 test document",
):
    return client.post(
        (
            f"/api/v1/customers/{customer_id}"
            f"/verification-cases/{verification_case_id}"
            "/documents"
        ),
        data={
            "document_type_id": str(document_type_id),
        },
        files={
            "file": (
                filename,
                BytesIO(content),
                content_type,
            ),
        },
    )


def test_upload_customer_document_success(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="document-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        first_name="Document",
        last_name="Customer",
        email="document-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    verification_response = create_verification_case(
        client,
        customer_id,
    )

    assert verification_response.status_code == 201

    verification_case_id = verification_response.json()["data"]["id"]

    document_type = get_passport_document_type(db_session)

    response = upload_document(
        client,
        customer_id,
        verification_case_id,
        document_type.id,
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["id"] is not None
    assert data["customer_id"] == str(customer_id)
    assert data["verification_case_id"] == str(verification_case_id)
    assert data["document_type_id"] == str(document_type.id)
    assert data["file_reference"] is not None
    assert data["file_name"] == "passport.pdf"
    assert data["file_type"] == "application/pdf"
    assert data["file_size"] > 0
    assert data["status"] == "UPLOADED"
    assert data["uploaded_by"] == str(admin.id)
    assert data["created_at"] is not None


def test_customer_document_metadata_is_stored(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="document-metadata-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        first_name="Metadata",
        last_name="Customer",
        email="document-metadata-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = UUID(customer_response.json()["data"]["id"])

    verification_response = create_verification_case(
        client,
        customer_id,
    )

    assert verification_response.status_code == 201

    verification_case_id = UUID(verification_response.json()["data"]["id"])

    document_type = get_passport_document_type(db_session)

    response = upload_document(
        client,
        customer_id,
        verification_case_id,
        document_type.id,
        filename="identity-document.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 identity document",
    )

    assert response.status_code == 201

    data = response.json()["data"]

    document = (
        db_session.query(CustomerDocument)
        .filter(
            CustomerDocument.id == data["id"],
        )
        .first()
    )

    assert document is not None
    assert document.customer_id == customer_id
    assert document.verification_case_id == verification_case_id
    assert document.document_type_id == document_type.id
    assert document.file_name == "identity-document.pdf"
    assert document.file_type == "application/pdf"
    assert document.file_size > 0
    assert document.status.value == "UPLOADED"
    assert document.uploaded_by == admin.id
    assert document.created_at is not None


def test_customer_document_links_to_file_record(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="document-file-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="document-file-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    verification_response = create_verification_case(
        client,
        customer_id,
    )

    assert verification_response.status_code == 201

    verification_case_id = verification_response.json()["data"]["id"]

    document_type = get_passport_document_type(db_session)

    response = upload_document(
        client,
        customer_id,
        verification_case_id,
        document_type.id,
    )

    assert response.status_code == 201

    data = response.json()["data"]

    document = (
        db_session.query(CustomerDocument)
        .filter(CustomerDocument.id == data["id"])
        .first()
    )

    assert document is not None
    assert document.file_reference is not None

    file_record = (
        db_session.query(File)
        .filter(
            File.id == document.file_reference,
        )
        .first()
    )

    assert file_record is not None
    assert file_record.original_filename == "passport.pdf"
    assert file_record.content_type == "application/pdf"
    assert file_record.file_size == document.file_size
    assert file_record.uploaded_by == admin.id


def test_upload_jpeg_document(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="document-jpeg-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="document-jpeg-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    verification_response = create_verification_case(
        client,
        customer_id,
    )

    assert verification_response.status_code == 201

    verification_case_id = verification_response.json()["data"]["id"]

    document_type = get_passport_document_type(db_session)

    response = upload_document(
        client,
        customer_id,
        verification_case_id,
        document_type.id,
        filename="passport.jpg",
        content_type="image/jpeg",
        content=b"\xff\xd8\xff\xe0 test jpeg",
    )

    assert response.status_code == 201
    assert response.json()["data"]["file_type"] == "image/jpeg"


def test_upload_png_document(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="document-png-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="document-png-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    verification_response = create_verification_case(
        client,
        customer_id,
    )

    assert verification_response.status_code == 201

    verification_case_id = verification_response.json()["data"]["id"]

    document_type = get_passport_document_type(db_session)

    response = upload_document(
        client,
        customer_id,
        verification_case_id,
        document_type.id,
        filename="passport.png",
        content_type="image/png",
        content=b"\x89PNG\r\n\x1a\n test png",
    )

    assert response.status_code == 201
    assert response.json()["data"]["file_type"] == "image/png"


def test_reject_unsupported_document_file_type(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="document-invalid-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="document-invalid-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    verification_response = create_verification_case(
        client,
        customer_id,
    )

    assert verification_response.status_code == 201

    verification_case_id = verification_response.json()["data"]["id"]

    document_type = get_passport_document_type(db_session)

    response = upload_document(
        client,
        customer_id,
        verification_case_id,
        document_type.id,
        filename="document.txt",
        content_type="text/plain",
        content=b"this must be rejected",
    )

    assert response.status_code == 400
    assert "not supported" in response.json()["message"].lower()


def test_reject_document_for_wrong_customer_case(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="document-wrong-case-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    first_customer_response = create_customer_with_data(
        client,
        first_name="First",
        last_name="Customer",
        email="document-first-customer@example.com",
    )

    assert first_customer_response.status_code == 201

    first_customer_id = first_customer_response.json()["data"]["id"]

    second_customer_response = create_customer_with_data(
        client,
        first_name="Second",
        last_name="Customer",
        email="document-second-customer@example.com",
    )

    assert second_customer_response.status_code == 201

    second_customer_id = second_customer_response.json()["data"]["id"]

    first_case_response = create_verification_case(
        client,
        first_customer_id,
    )

    assert first_case_response.status_code == 201

    second_case_response = create_verification_case(
        client,
        second_customer_id,
    )

    assert second_case_response.status_code == 201

    second_case_id = second_case_response.json()["data"]["id"]

    document_type = get_passport_document_type(db_session)

    response = upload_document(
        client,
        first_customer_id,
        second_case_id,
        document_type.id,
    )

    assert response.status_code == 404


def test_reject_document_with_inactive_document_type(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
    reset_verification_document_types,
):
    _, admin = create_test_user(
        email="document-inactive-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="document-inactive-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    verification_response = create_verification_case(
        client,
        customer_id,
    )

    assert verification_response.status_code == 201

    verification_case_id = verification_response.json()["data"]["id"]

    document_type = get_passport_document_type(db_session)

    document_type.is_active = False
    db_session.commit()

    response = upload_document(
        client,
        customer_id,
        verification_case_id,
        document_type.id,
    )

    assert response.status_code == 400
    assert "active" in response.json()["message"].lower()


def test_get_customer_documents(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="document-list-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="document-list-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    verification_response = create_verification_case(
        client,
        customer_id,
    )

    assert verification_response.status_code == 201

    verification_case_id = verification_response.json()["data"]["id"]

    document_type = get_passport_document_type(db_session)

    first_upload = upload_document(
        client,
        customer_id,
        verification_case_id,
        document_type.id,
        filename="passport-1.pdf",
    )

    second_upload = upload_document(
        client,
        customer_id,
        verification_case_id,
        document_type.id,
        filename="passport-2.pdf",
    )

    assert first_upload.status_code == 201
    assert second_upload.status_code == 201

    response = client.get(
        (
            f"/api/v1/customers/{customer_id}"
            f"/verification-cases/{verification_case_id}"
            "/documents"
        )
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["total"] == 2
    assert len(data["documents"]) == 2


def test_get_customer_document_by_id(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="document-get-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="document-get-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    verification_response = create_verification_case(
        client,
        customer_id,
    )

    assert verification_response.status_code == 201

    verification_case_id = verification_response.json()["data"]["id"]

    document_type = get_passport_document_type(db_session)

    upload_response = upload_document(
        client,
        customer_id,
        verification_case_id,
        document_type.id,
    )

    assert upload_response.status_code == 201

    document_id = upload_response.json()["data"]["id"]

    response = client.get(
        (
            f"/api/v1/customers/{customer_id}"
            f"/verification-cases/{verification_case_id}"
            f"/documents/{document_id}"
        )
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["id"] == document_id
    assert data["customer_id"] == str(customer_id)
    assert data["verification_case_id"] == str(verification_case_id)


def test_standard_user_cannot_upload_customer_document(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="document-standard-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="document-standard-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    verification_response = create_verification_case(
        client,
        customer_id,
    )

    assert verification_response.status_code == 201

    verification_case_id = verification_response.json()["data"]["id"]

    document_type = get_passport_document_type(db_session)

    _, standard_user = create_test_user(
        email="document-standard-user@example.com",
        role=UserRole.AUDITOR,
    )

    authenticate_client(client, standard_user)

    response = upload_document(
        client,
        customer_id,
        verification_case_id,
        document_type.id,
    )

    assert response.status_code == 403


def test_reviewer_can_retrieve_customer_documents(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="document-reviewer-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="document-reviewer-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    verification_response = create_verification_case(
        client,
        customer_id,
    )

    assert verification_response.status_code == 201

    verification_case_id = verification_response.json()["data"]["id"]

    document_type = get_passport_document_type(db_session)

    upload_response = upload_document(
        client,
        customer_id,
        verification_case_id,
        document_type.id,
    )

    assert upload_response.status_code == 201

    _, reviewer = create_test_user(
        email="document-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, reviewer)

    response = client.get(
        (
            f"/api/v1/customers/{customer_id}"
            f"/verification-cases/{verification_case_id}"
            "/documents"
        )
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["total"] == 1
    assert len(data["documents"]) == 1
