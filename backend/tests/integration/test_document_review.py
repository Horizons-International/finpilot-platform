import uuid
from datetime import date
from typing import cast

from app.extraction.providers.base import ExtractionProvider
from app.extraction.schemas.responses import DocumentExtractionResponse
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.document_extraction import DocumentExtraction
from app.models.document_extraction_review_log import (
    DocumentExtractionReviewLog,
)
from app.models.ocr_result import OCRResult
from app.utils.enums import (
    AuditEventType,
    ExtractionReviewStatus,
    ExtractionStatus,
    OCRProcessingStatus,
    UserRole,
)
from tests.helpers import (
    authenticate_client,
    create_customer_with_data,
    create_verification_case,
    get_passport_document_type,
    upload_document,
)

# ---------------------------------------------------------------------------
# Test provider
# ---------------------------------------------------------------------------


class FakeExtractionProvider(ExtractionProvider):
    def __init__(
        self,
        response: DocumentExtractionResponse | None = None,
    ) -> None:
        self.response = response
        self.document_ids: list[uuid.UUID] = []
        self.ocr_texts: list[str] = []

    def extract(
        self,
        *,
        document_id: uuid.UUID,
        ocr_text: str,
    ) -> DocumentExtractionResponse:
        self.document_ids.append(document_id)
        self.ocr_texts.append(ocr_text)

        if self.response is None:
            raise RuntimeError("Fake extraction provider has no configured response.")

        return self.response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def create_extraction_response() -> DocumentExtractionResponse:
    return DocumentExtractionResponse(
        first_name="John",
        middle_name="Michael",
        last_name="Doe",
        date_of_birth=date(1990, 1, 1),
        nationality="Sudanese",
        document_number="P123456",
        expiry_date=date(2030, 1, 1),
        address="Khartoum, Sudan",
    )


def create_review_document(
    client,
    db_session,
    *,
    setup_user,
    extraction_service_override,
    customer_first_name: str = "Original",
    customer_middle_name: str | None = "Customer",
    customer_last_name: str = "Name",
):
    """
    Create a complete document/OCR/extraction setup ready for review.

    The setup user must have permission to create customers and upload
    documents. Review actions are authenticated separately by each test.
    """

    authenticate_client(client, setup_user)

    customer_response = create_customer_with_data(
        client,
        first_name=customer_first_name,
        middle_name=customer_middle_name,
        last_name=customer_last_name,
        email=f"review-{uuid.uuid4()}@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = uuid.UUID(
        customer_response.json()["data"]["id"],
    )

    verification_response = create_verification_case(
        client,
        customer_id,
    )

    verification_case_id = verification_response["id"]

    document_type = get_passport_document_type(db_session)

    upload_response = upload_document(
        client,
        customer_id,
        verification_case_id,
        document_type.id,
        filename="identity-document.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 identity document",
    )

    assert upload_response.status_code == 201

    document_id = uuid.UUID(
        upload_response.json()["data"]["id"],
    )

    file_id = upload_response.json()["data"]["file_reference"]

    ocr_result = OCRResult(
        document_id=document_id,
        provider_name="mock",
        request_id=uuid.uuid4(),
        extracted_text=(
            "John Michael Doe\nPassport Number: P123456\nNationality: Sudanese"
        ),
        status=OCRProcessingStatus.COMPLETED,
    )

    db_session.add(ocr_result)
    db_session.commit()
    db_session.refresh(ocr_result)

    provider = FakeExtractionProvider(
        response=create_extraction_response(),
    )

    extraction_service_override(provider)

    extraction_response = client.post(
        f"/api/v1/documents/{document_id}/extraction",
    )

    assert extraction_response.status_code == 201

    extraction_id = uuid.UUID(
        extraction_response.json()["data"]["id"],
    )

    extraction = (
        db_session.query(DocumentExtraction)
        .filter(DocumentExtraction.id == extraction_id)
        .first()
    )

    assert extraction is not None
    assert extraction.status == ExtractionStatus.COMPLETED
    assert extraction.review_status == ExtractionReviewStatus.PENDING_REVIEW

    return (
        customer_id,
        document_id,
        ocr_result,
        extraction,
        file_id,
    )


def get_customer(
    db_session,
    customer_id: uuid.UUID,
) -> Customer:
    customer = db_session.query(Customer).filter(Customer.id == customer_id).first()

    if customer is None:
        raise AssertionError(f"Customer {customer_id} was not found.")

    return cast(Customer, customer)


# ---------------------------------------------------------------------------
# GET /documents/{document_id}/review
# ---------------------------------------------------------------------------


def test_get_document_review_returns_comparison_data(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    extraction_service_override,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin-get@example.com",
    )

    reviewer = create_test_user(
        role=UserRole.REVIEWER,
        email="review-get@example.com",
    )

    (
        customer_id,
        document_id,
        ocr_result,
        extraction,
        file_id,
    ) = create_review_document(
        client,
        db_session,
        setup_user=admin,
        extraction_service_override=extraction_service_override,
    )

    authenticate_client(client, reviewer)

    response = client.get(
        f"/api/v1/documents/{document_id}/review",
    )

    cleanup_test_files(file_id)

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True

    data = body["data"]

    assert data["document"]["id"] == str(document_id)

    assert data["ocr_result"]["id"] == str(ocr_result.id)
    assert data["ocr_result"]["document_id"] == str(document_id)
    assert data["ocr_result"]["status"] == (OCRProcessingStatus.COMPLETED.value)

    assert data["extraction"]["id"] == str(extraction.id)
    assert data["extraction"]["document_id"] == str(document_id)
    assert data["extraction"]["ocr_result_id"] == str(ocr_result.id)
    assert data["extraction"]["extraction_status"] == ExtractionStatus.COMPLETED.value
    assert data["extraction"]["review_status"] == (
        ExtractionReviewStatus.PENDING_REVIEW.value
    )

    assert data["extraction"]["first_name"] == "John"
    assert data["extraction"]["middle_name"] == "Michael"
    assert data["extraction"]["last_name"] == "Doe"
    assert data["extraction"]["document_number"] == "P123456"

    assert data["customer"]["id"] == str(customer_id)
    assert data["customer"]["first_name"] == "Original"
    assert data["customer"]["middle_name"] == "Customer"
    assert data["customer"]["last_name"] == "Name"


def test_get_document_review_requires_authentication(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    extraction_service_override,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="review-authentication@example.com",
    )

    (
        _customer_id,
        document_id,
        _ocr_result,
        _extraction,
        file_id,
    ) = create_review_document(
        client,
        db_session,
        setup_user=admin,
        extraction_service_override=extraction_service_override,
    )

    client.headers.pop("Authorization", None)

    response = client.get(
        f"/api/v1/documents/{document_id}/review",
    )

    cleanup_test_files(file_id)

    assert response.status_code == 401


def test_get_document_review_allows_compliance_officer(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    extraction_service_override,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin-get@example.com",
    )

    compliance_officer = create_test_user(
        role=UserRole.COMPLIANCE_OFFICER,
        email="review-compliance@example.com",
    )

    (
        _customer_id,
        document_id,
        _ocr_result,
        _extraction,
        file_id,
    ) = create_review_document(
        client,
        db_session,
        setup_user=admin,
        extraction_service_override=extraction_service_override,
    )

    authenticate_client(client, compliance_officer)

    response = client.get(
        f"/api/v1/documents/{document_id}/review",
    )

    cleanup_test_files(file_id)

    assert response.status_code == 200


def test_get_document_review_allows_administrator(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    extraction_service_override,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="review-administrator@example.com",
    )

    _customer_id, document_id, _ocr_result, _extraction, file_id = (
        create_review_document(
            client,
            db_session,
            setup_user=admin,
            extraction_service_override=extraction_service_override,
        )
    )

    response = client.get(
        f"/api/v1/documents/{document_id}/review",
    )

    cleanup_test_files(file_id)

    assert response.status_code == 200


def test_get_document_review_rejects_auditor(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    extraction_service_override,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="review-auditor-admin@example.com",
    )

    (
        _customer_id,
        document_id,
        _ocr_result,
        _extraction,
        file_id,
    ) = create_review_document(
        client,
        db_session,
        setup_user=admin,
        extraction_service_override=extraction_service_override,
    )

    auditor = create_test_user(
        role=UserRole.AUDITOR,
        email="review-auditor@example.com",
    )

    authenticate_client(client, auditor)

    cleanup_test_files(file_id)

    response = client.get(
        f"/api/v1/documents/{document_id}/review",
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /documents/{document_id}/review
# ---------------------------------------------------------------------------


def test_update_document_review_updates_extraction_only(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    extraction_service_override,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin-get@example.com",
    )

    reviewer = create_test_user(
        role=UserRole.REVIEWER,
        email="review-update@example.com",
    )

    (
        customer_id,
        document_id,
        _ocr_result,
        extraction,
        file_id,
    ) = create_review_document(
        client,
        db_session,
        setup_user=admin,
        extraction_service_override=extraction_service_override,
    )

    authenticate_client(client, reviewer)

    response = client.patch(
        f"/api/v1/documents/{document_id}/review",
        json={
            "first_name": "Jonathan",
            "document_number": "P999999",
        },
    )

    cleanup_test_files(file_id)

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["data"]["first_name"] == "Jonathan"
    assert body["data"]["document_number"] == "P999999"
    assert body["data"]["review_status"] == (
        ExtractionReviewStatus.PENDING_REVIEW.value
    )

    db_session.expire_all()

    updated_extraction = (
        db_session.query(DocumentExtraction)
        .filter(DocumentExtraction.id == extraction.id)
        .first()
    )

    assert updated_extraction is not None
    assert updated_extraction.first_name == "Jonathan"
    assert updated_extraction.document_number == "P999999"
    assert updated_extraction.review_status == (ExtractionReviewStatus.PENDING_REVIEW)

    customer = get_customer(
        db_session,
        customer_id,
    )

    assert customer.first_name == "Original"
    assert customer.last_name == "Name"


def test_update_document_review_records_field_changes(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    extraction_service_override,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin-get@example.com",
    )

    reviewer = create_test_user(
        role=UserRole.REVIEWER,
        email="review-history@example.com",
    )

    (
        _customer_id,
        document_id,
        _ocr_result,
        extraction,
        file_id,
    ) = create_review_document(
        client,
        db_session,
        setup_user=admin,
        extraction_service_override=extraction_service_override,
    )

    authenticate_client(client, reviewer)

    response = client.patch(
        f"/api/v1/documents/{document_id}/review",
        json={
            "first_name": "Jonathan",
            "document_number": "P999999",
        },
    )

    cleanup_test_files(file_id)

    assert response.status_code == 200

    logs = (
        db_session.query(DocumentExtractionReviewLog)
        .filter(
            DocumentExtractionReviewLog.document_extraction_id == extraction.id,
            DocumentExtractionReviewLog.reviewer_id == reviewer.id,
        )
        .all()
    )

    assert len(logs) == 2

    changes = {log.field_name: (log.old_value, log.new_value) for log in logs}

    assert changes["first_name"] == ("John", "Jonathan")
    assert changes["document_number"] == ("P123456", "P999999")


def test_update_document_review_does_not_record_unchanged_fields(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    extraction_service_override,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin-get@example.com",
    )

    reviewer = create_test_user(
        role=UserRole.REVIEWER,
        email="review-no-change@example.com",
    )

    (
        _customer_id,
        document_id,
        _ocr_result,
        extraction,
        file_id,
    ) = create_review_document(
        client,
        db_session,
        setup_user=admin,
        extraction_service_override=extraction_service_override,
    )

    authenticate_client(client, reviewer)

    response = client.patch(
        f"/api/v1/documents/{document_id}/review",
        json={
            "first_name": "John",
        },
    )

    cleanup_test_files(file_id)

    assert response.status_code == 200

    logs = (
        db_session.query(DocumentExtractionReviewLog)
        .filter(
            DocumentExtractionReviewLog.document_extraction_id == extraction.id,
        )
        .all()
    )

    assert logs == []


def test_update_document_review_requires_fields(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    extraction_service_override,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin-get@example.com",
    )

    reviewer = create_test_user(
        role=UserRole.REVIEWER,
        email="review-empty-update@example.com",
    )

    (
        _customer_id,
        document_id,
        _ocr_result,
        _extraction,
        file_id,
    ) = create_review_document(
        client,
        db_session,
        setup_user=admin,
        extraction_service_override=extraction_service_override,
    )

    authenticate_client(client, reviewer)

    response = client.patch(
        f"/api/v1/documents/{document_id}/review",
        json={},
    )

    cleanup_test_files(file_id)

    assert response.status_code == 400

    body = response.json()

    assert body["message"] == ("No extraction fields were provided for update.")


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------


def test_approve_document_review_updates_customer(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    extraction_service_override,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin-get@example.com",
    )

    reviewer = create_test_user(
        role=UserRole.REVIEWER,
        email="review-approve@example.com",
    )

    (
        customer_id,
        document_id,
        _ocr_result,
        extraction,
        file_id,
    ) = create_review_document(
        client,
        db_session,
        setup_user=admin,
        extraction_service_override=extraction_service_override,
    )

    authenticate_client(client, reviewer)

    response = client.post(
        f"/api/v1/documents/{document_id}/review/approve",
    )

    cleanup_test_files(file_id)

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["data"]["id"] == str(extraction.id)
    assert body["data"]["review_status"] == (ExtractionReviewStatus.APPROVED.value)
    assert body["data"]["reviewed_by"] == str(reviewer.id)
    assert body["data"]["reviewed_at"] is not None
    assert body["data"]["rejection_reason"] is None

    db_session.expire_all()

    updated_customer = get_customer(
        db_session,
        customer_id,
    )

    assert updated_customer.first_name == "John"
    assert updated_customer.middle_name == "Michael"
    assert updated_customer.last_name == "Doe"
    assert updated_customer.date_of_birth == date(1990, 1, 1)
    assert updated_customer.nationality == "Sudanese"


def test_approve_document_review_preserves_customer_fields_missing_from_extraction(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin-get@example.com",
    )

    authenticate_client(client, admin)

    reviewer = create_test_user(
        role=UserRole.REVIEWER,
        email="review-approve-partial@example.com",
    )

    customer_response = create_customer_with_data(
        client,
        first_name="Existing",
        middle_name="Middle",
        last_name="Customer",
        date_of_birth="1985-05-10",
        nationality="Sudanese",
        email=f"partial-{uuid.uuid4()}@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = uuid.UUID(
        customer_response.json()["data"]["id"],
    )

    verification_response = create_verification_case(
        client,
        customer_id,
    )

    document_type = get_passport_document_type(db_session)

    upload_response = upload_document(
        client,
        customer_id,
        verification_response["id"],
        document_type.id,
    )

    assert upload_response.status_code == 201

    document_id = uuid.UUID(
        upload_response.json()["data"]["id"],
    )

    ocr_result = OCRResult(
        document_id=document_id,
        provider_name="mock",
        request_id=uuid.uuid4(),
        extracted_text="John Doe",
        status=OCRProcessingStatus.COMPLETED,
    )

    db_session.add(ocr_result)
    db_session.flush()

    extraction = DocumentExtraction(
        document_id=document_id,
        ocr_result_id=ocr_result.id,
        provider_name="FakeExtractionProvider",
        status=ExtractionStatus.COMPLETED,
        review_status=ExtractionReviewStatus.PENDING_REVIEW,
        first_name="John",
        middle_name=None,
        last_name="Doe",
        date_of_birth=None,
        nationality=None,
        document_number="P123456",
        expiry_date=None,
        address=None,
    )

    db_session.add(extraction)
    db_session.commit()

    authenticate_client(client, reviewer)

    response = client.post(
        f"/api/v1/documents/{document_id}/review/approve",
    )

    cleanup_test_files(upload_response.json()["data"]["file_reference"])

    assert response.status_code == 200

    db_session.expire_all()

    customer = get_customer(
        db_session,
        customer_id,
    )

    assert customer.first_name == "John"
    assert customer.middle_name == "Middle"
    assert customer.last_name == "Doe"
    assert customer.date_of_birth == date(1985, 5, 10)
    assert customer.nationality == "Sudanese"


def test_approve_document_review_is_immutable(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    extraction_service_override,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin-get@example.com",
    )

    reviewer = create_test_user(
        role=UserRole.REVIEWER,
        email="review-approve-immutable@example.com",
    )

    (
        _customer_id,
        document_id,
        _ocr_result,
        _extraction,
        file_id,
    ) = create_review_document(
        client,
        db_session,
        setup_user=admin,
        extraction_service_override=extraction_service_override,
    )

    authenticate_client(client, reviewer)

    approve_response = client.post(
        f"/api/v1/documents/{document_id}/review/approve",
    )

    assert approve_response.status_code == 200

    patch_response = client.patch(
        f"/api/v1/documents/{document_id}/review",
        json={
            "first_name": "ChangedAfterApproval",
        },
    )

    cleanup_test_files(file_id)

    assert patch_response.status_code == 400
    assert patch_response.json()["message"] == (
        "Document extraction has already been reviewed."
    )

    second_approve_response = client.post(
        f"/api/v1/documents/{document_id}/review/approve",
    )

    assert second_approve_response.status_code == 400
    assert second_approve_response.json()["message"] == (
        "Document extraction has already been reviewed."
    )


# ---------------------------------------------------------------------------
# Rejection
# ---------------------------------------------------------------------------


def test_reject_document_review_stores_reason(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    extraction_service_override,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin-get@example.com",
    )

    reviewer = create_test_user(
        role=UserRole.REVIEWER,
        email="review-reject@example.com",
    )

    (
        _customer_id,
        document_id,
        _ocr_result,
        extraction,
        file_id,
    ) = create_review_document(
        client,
        db_session,
        setup_user=admin,
        extraction_service_override=extraction_service_override,
    )

    authenticate_client(client, reviewer)

    reason = "Document number does not match the physical document."

    response = client.post(
        f"/api/v1/documents/{document_id}/review/reject",
        json={
            "reason": reason,
        },
    )

    cleanup_test_files(file_id)

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["data"]["id"] == str(extraction.id)
    assert body["data"]["review_status"] == (ExtractionReviewStatus.REJECTED.value)
    assert body["data"]["reviewed_by"] == str(reviewer.id)
    assert body["data"]["reviewed_at"] is not None
    assert body["data"]["rejection_reason"] == reason


def test_reject_document_review_does_not_update_customer(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    extraction_service_override,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin-get@example.com",
    )

    reviewer = create_test_user(
        role=UserRole.REVIEWER,
        email="review-reject-customer@example.com",
    )

    (
        customer_id,
        document_id,
        _ocr_result,
        _extraction,
        file_id,
    ) = create_review_document(
        client,
        db_session,
        setup_user=admin,
        extraction_service_override=extraction_service_override,
    )

    authenticate_client(client, reviewer)

    response = client.post(
        f"/api/v1/documents/{document_id}/review/reject",
        json={
            "reason": "Incorrect identity information.",
        },
    )

    cleanup_test_files(file_id)

    assert response.status_code == 200

    db_session.expire_all()

    customer = get_customer(
        db_session,
        customer_id,
    )

    assert customer.first_name == "Original"
    assert customer.middle_name == "Customer"
    assert customer.last_name == "Name"


def test_reject_document_review_requires_reason(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    extraction_service_override,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin-get@example.com",
    )

    reviewer = create_test_user(
        role=UserRole.REVIEWER,
        email="review-reject-no-reason@example.com",
    )

    (
        _customer_id,
        document_id,
        _ocr_result,
        _extraction,
        file_id,
    ) = create_review_document(
        client,
        db_session,
        setup_user=admin,
        extraction_service_override=extraction_service_override,
    )

    authenticate_client(client, reviewer)

    response = client.post(
        f"/api/v1/documents/{document_id}/review/reject",
        json={
            "reason": "   ",
        },
    )

    cleanup_test_files(file_id)

    assert response.status_code == 400


def test_reject_document_review_is_immutable(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    extraction_service_override,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin-get@example.com",
    )

    reviewer = create_test_user(
        role=UserRole.REVIEWER,
        email="review-reject-immutable@example.com",
    )

    (
        _customer_id,
        document_id,
        _ocr_result,
        _extraction,
        file_id,
    ) = create_review_document(
        client,
        db_session,
        setup_user=admin,
        extraction_service_override=extraction_service_override,
    )

    authenticate_client(client, reviewer)

    reject_response = client.post(
        f"/api/v1/documents/{document_id}/review/reject",
        json={
            "reason": "Rejected by compliance review.",
        },
    )

    cleanup_test_files(file_id)

    assert reject_response.status_code == 200

    patch_response = client.patch(
        f"/api/v1/documents/{document_id}/review",
        json={
            "first_name": "ChangedAfterRejection",
        },
    )

    assert patch_response.status_code == 400
    assert patch_response.json()["message"] == (
        "Document extraction has already been reviewed."
    )

    approve_response = client.post(
        f"/api/v1/documents/{document_id}/review/approve",
    )

    assert approve_response.status_code == 400
    assert approve_response.json()["message"] == (
        "Document extraction has already been reviewed."
    )


# ---------------------------------------------------------------------------
# Invalid review state / missing data
# ---------------------------------------------------------------------------


def test_get_review_fails_without_completed_ocr(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin-get@example.com",
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email=f"no-ocr-{uuid.uuid4()}@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = uuid.UUID(
        customer_response.json()["data"]["id"],
    )

    verification_response = create_verification_case(
        client,
        customer_id,
    )

    document_type = get_passport_document_type(db_session)

    upload_response = upload_document(
        client,
        customer_id,
        verification_response["id"],
        document_type.id,
    )

    assert upload_response.status_code == 201

    document_id = uuid.UUID(
        upload_response.json()["data"]["id"],
    )

    response = client.get(
        f"/api/v1/documents/{document_id}/review",
    )

    cleanup_test_files(upload_response.json()["data"]["file_reference"])

    assert response.status_code == 400

    assert response.json()["message"] == (
        "Document has no completed OCR result available for review."
    )


def test_get_review_fails_without_extraction(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin-get@example.com",
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email=f"no-extraction-{uuid.uuid4()}@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = uuid.UUID(
        customer_response.json()["data"]["id"],
    )

    verification_response = create_verification_case(
        client,
        customer_id,
    )

    document_type = get_passport_document_type(db_session)

    upload_response = upload_document(
        client,
        customer_id,
        verification_response["id"],
        document_type.id,
    )

    assert upload_response.status_code == 201

    document_id = uuid.UUID(
        upload_response.json()["data"]["id"],
    )

    ocr_result = OCRResult(
        document_id=document_id,
        provider_name="mock",
        request_id=uuid.uuid4(),
        extracted_text="John Doe",
        status=OCRProcessingStatus.COMPLETED,
    )

    db_session.add(ocr_result)
    db_session.commit()

    response = client.get(
        f"/api/v1/documents/{document_id}/review",
    )

    cleanup_test_files(upload_response.json()["data"]["file_reference"])

    assert response.status_code == 400

    assert response.json()["message"] == (
        "Document has no extraction result available for review."
    )


def test_update_review_cannot_modify_approved_extraction(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    extraction_service_override,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin-get@example.com",
    )

    reviewer = create_test_user(
        role=UserRole.REVIEWER,
        email="review-approved-update@example.com",
    )

    (
        _customer_id,
        document_id,
        _ocr_result,
        _extraction,
        file_id,
    ) = create_review_document(
        client,
        db_session,
        setup_user=admin,
        extraction_service_override=extraction_service_override,
    )

    authenticate_client(client, reviewer)

    approve_response = client.post(
        f"/api/v1/documents/{document_id}/review/approve",
    )

    assert approve_response.status_code == 200

    response = client.patch(
        f"/api/v1/documents/{document_id}/review",
        json={
            "last_name": "Modified",
        },
    )

    cleanup_test_files(file_id)

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Audit events
# ---------------------------------------------------------------------------


def test_review_update_creates_audit_event(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    extraction_service_override,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin-get@example.com",
    )

    reviewer = create_test_user(
        role=UserRole.REVIEWER,
        email="review-audit-update@example.com",
    )

    (
        _customer_id,
        document_id,
        _ocr_result,
        extraction,
        file_id,
    ) = create_review_document(
        client,
        db_session,
        setup_user=admin,
        extraction_service_override=extraction_service_override,
    )

    authenticate_client(client, reviewer)

    response = client.patch(
        f"/api/v1/documents/{document_id}/review",
        json={
            "first_name": "Jonathan",
        },
    )

    cleanup_test_files(file_id)

    assert response.status_code == 200

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == reviewer.id,
            AuditLog.event_type == AuditEventType.DOCUMENT_EXTRACTION_REVIEW_UPDATED,
            AuditLog.resource_id == extraction.id,
        )
        .first()
    )

    assert audit_log is not None


def test_review_approval_creates_audit_event(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    extraction_service_override,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin-get@example.com",
    )

    reviewer = create_test_user(
        role=UserRole.REVIEWER,
        email="review-audit-approve@example.com",
    )

    (
        _customer_id,
        document_id,
        _ocr_result,
        extraction,
        file_id,
    ) = create_review_document(
        client,
        db_session,
        setup_user=admin,
        extraction_service_override=extraction_service_override,
    )

    authenticate_client(client, reviewer)

    response = client.post(
        f"/api/v1/documents/{document_id}/review/approve",
    )

    cleanup_test_files(file_id)

    assert response.status_code == 200

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == reviewer.id,
            AuditLog.event_type == AuditEventType.DOCUMENT_EXTRACTION_REVIEW_APPROVED,
            AuditLog.resource_id == extraction.id,
        )
        .first()
    )

    assert audit_log is not None


def test_review_rejection_creates_audit_event(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    extraction_service_override,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin-get@example.com",
    )

    reviewer = create_test_user(
        role=UserRole.REVIEWER,
        email="review-audit-reject@example.com",
    )

    (
        _customer_id,
        document_id,
        _ocr_result,
        extraction,
        file_id,
    ) = create_review_document(
        client,
        db_session,
        setup_user=admin,
        extraction_service_override=extraction_service_override,
    )

    authenticate_client(client, reviewer)

    response = client.post(
        f"/api/v1/documents/{document_id}/review/reject",
        json={
            "reason": "Rejected during compliance review.",
        },
    )

    cleanup_test_files(file_id)

    assert response.status_code == 200

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == reviewer.id,
            AuditLog.event_type == AuditEventType.DOCUMENT_EXTRACTION_REVIEW_REJECTED,
            AuditLog.resource_id == extraction.id,
        )
        .first()
    )

    assert audit_log is not None
