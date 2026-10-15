"""Integration tests for document fraud screening and tenant isolation."""

from datetime import date
from uuid import UUID, uuid4

import pytest

from app.models.document import CustomerDocument
from app.models.document_extraction import DocumentExtraction
from app.models.document_fraud_analysis import DocumentFraudAnalysis
from app.models.ocr_result import OCRResult
from app.utils.enums import (
    DocumentStatus,
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
)


@pytest.fixture
def cleanup_document_fraud_analyses(db_session):
    existing_ids = {
        analysis.id for analysis in db_session.query(DocumentFraudAnalysis).all()
    }
    yield
    for analysis in db_session.query(DocumentFraudAnalysis).all():
        if analysis.id not in existing_ids:
            db_session.delete(analysis)
    db_session.commit()


def _create_customer_and_documents(client, creator, db_session, *, count=2):
    authenticate_client(client, creator)
    customer_response = create_customer_with_data(
        client,
        email=f"document-fraud-{uuid4()}@example.com",
        first_name="John",
        last_name="Smith",
        date_of_birth="1990-05-15",
        nationality="US",
    )
    assert customer_response.status_code == 201, customer_response.text
    customer_id = UUID(customer_response.json()["data"]["id"])
    verification_case = create_verification_case(client, customer_id)
    document_type = get_passport_document_type(db_session)
    documents = []
    for index in range(count):
        document = CustomerDocument(
            tenant_id=creator.tenant_id,
            customer_id=customer_id,
            verification_case_id=UUID(verification_case["id"]),
            document_type_id=document_type.id,
            file_reference=f"test-document-fraud-{uuid4()}",
            file_name=f"passport-{index}.pdf",
            file_type="application/pdf",
            file_size=8192,
            status=DocumentStatus.UPLOADED,
            uploaded_by=creator.id,
        )
        db_session.add(document)
        db_session.flush()
        documents.append(document.id)
    db_session.commit()
    return customer_id, documents


def _seed_ocr_and_extraction(
    db_session,
    *,
    tenant_id,
    document_id,
    first_name: str,
    document_number: str,
    ocr_text: str,
):
    ocr = OCRResult(
        tenant_id=tenant_id,
        document_id=document_id,
        provider_name="test",
        extracted_text=ocr_text,
        status=OCRProcessingStatus.COMPLETED,
    )
    db_session.add(ocr)
    db_session.flush()
    extraction = DocumentExtraction(
        tenant_id=tenant_id,
        document_id=document_id,
        ocr_result_id=ocr.id,
        provider_name="test",
        status=ExtractionStatus.COMPLETED,
        review_status=ExtractionReviewStatus.PENDING_REVIEW,
        first_name=first_name,
        last_name="Smith",
        date_of_birth=date(1990, 5, 15),
        nationality="US",
        document_number=document_number,
        expiry_date=date(2030, 1, 1),
    )
    db_session.add(extraction)
    db_session.commit()


def test_document_fraud_analysis_flags_name_and_duplicate_and_is_stored(
    client,
    db_session,
    create_test_user,
    cleanup_ai_data,
    cleanup_test_customers,
    cleanup_document_fraud_analyses,
):
    admin = create_test_user(
        email=f"document-fraud-admin-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    compliance_officer = create_test_user(
        email=f"document-fraud-compliance-{uuid4()}@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )
    customer_id, document_ids = _create_customer_and_documents(
        client, admin, db_session, count=2
    )
    _seed_ocr_and_extraction(
        db_session,
        tenant_id=admin.tenant_id,
        document_id=document_ids[0],
        first_name="Jon",
        document_number="P-123456",
        ocr_text=(
            "PASSPORT JON SMITH DOCUMENT NUMBER P-123456 DATE OF BIRTH "
            "15 MAY 1990 NATIONALITY US EXPIRY 01 JAN 2030"
        ),
    )
    _seed_ocr_and_extraction(
        db_session,
        tenant_id=admin.tenant_id,
        document_id=document_ids[1],
        first_name="John",
        document_number="P-123456",
        ocr_text=(
            "SECOND PASSPORT COPY JOHN SMITH DOCUMENT NUMBER P-123456 DATE OF BIRTH "
            "15 MAY 1990 NATIONALITY US EXPIRY 01 JAN 2030"
        ),
    )

    authenticate_client(client, compliance_officer)
    response = client.post(
        f"/api/v1/document-fraud/documents/{document_ids[0]}/analyze",
        json={"use_ai": True},
    )
    assert response.status_code == 201, response.text
    payload = response.json()["data"]
    assert payload["status"] == "COMPLETED"
    assert payload["customer_id"] == str(customer_id)
    assert payload["risk_score"] >= 0
    assert payload["needs_manual_review"] is True
    assert payload["result"]["ai_enrichment_available"] is True
    assert any(
        item["code"] == "CUSTOMER_NAME_MISMATCH"
        for item in payload["result"]["inconsistencies"]
    )
    assert any(
        item["match_type"] == "DOCUMENT_NUMBER"
        for item in payload["result"]["duplicate_matches"]
    )

    analysis_id = payload["id"]
    detail = client.get(f"/api/v1/document-fraud/analyses/{analysis_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["result"]["summary"]

    history = client.get(
        "/api/v1/document-fraud/analyses",
        params={"customer_id": str(customer_id)},
    )
    assert history.status_code == 200, history.text
    assert any(item["id"] == analysis_id for item in history.json()["data"]["items"])


def test_document_fraud_analysis_is_tenant_scoped(
    client,
    db_session,
    create_test_user,
    create_test_tenant,
    cleanup_test_customers,
    cleanup_document_fraud_analyses,
):
    admin = create_test_user(
        email=f"document-fraud-owner-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    _, document_ids = _create_customer_and_documents(client, admin, db_session, count=1)
    _seed_ocr_and_extraction(
        db_session,
        tenant_id=admin.tenant_id,
        document_id=document_ids[0],
        first_name="John",
        document_number="P-998877",
        ocr_text=(
            "PASSPORT JOHN SMITH DOCUMENT NUMBER P-998877 DATE OF BIRTH "
            "15 MAY 1990 NATIONALITY US EXPIRY 01 JAN 2030"
        ),
    )
    response = client.post(
        f"/api/v1/document-fraud/documents/{document_ids[0]}/analyze",
        json={"use_ai": False},
    )
    assert response.status_code == 201, response.text
    analysis_id = response.json()["data"]["id"]

    other_tenant = create_test_tenant()
    other_user = create_test_user(
        email=f"document-fraud-other-{uuid4()}@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
        tenant_id=other_tenant.id,
    )
    authenticate_client(client, other_user)
    hidden = client.get(f"/api/v1/document-fraud/analyses/{analysis_id}")
    assert hidden.status_code == 404


def test_document_fraud_analysis_returns_not_found_for_unknown_document(
    client,
    create_test_user,
):
    officer = create_test_user(
        email=f"document-fraud-missing-{uuid4()}@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )
    authenticate_client(client, officer)
    response = client.post(
        f"/api/v1/document-fraud/documents/{uuid4()}/analyze",
        json={"use_ai": False},
    )
    assert response.status_code == 404
