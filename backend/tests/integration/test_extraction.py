import uuid
from datetime import date
from pathlib import Path
from shutil import rmtree
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.extraction.exceptions import (
    ExtractionProviderError,
    ExtractionResponseError,
)
from app.extraction.providers.base import ExtractionProvider
from app.extraction.providers.factory import get_extraction_provider
from app.extraction.providers.mock import MockExtractionProvider
from app.extraction.schemas.responses import DocumentExtractionResponse
from app.extraction.services.extraction_service import DocumentExtractionService
from app.models.audit_log import AuditLog
from app.models.document import CustomerDocument
from app.models.document_extraction import DocumentExtraction
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


@pytest.fixture(autouse=True)
def cleanup_extraction_storage():
    verification_root = Path(settings.STORAGE_PATH) / "verification"

    existing_folders = set()

    if verification_root.exists():
        existing_folders = {
            folder for folder in verification_root.iterdir() if folder.is_dir()
        }

    yield

    if not verification_root.exists():
        return

    for folder in verification_root.iterdir():
        if folder.is_dir() and folder not in existing_folders:
            rmtree(folder, ignore_errors=True)


def test_document_extraction_response_accepts_complete_data():
    result = DocumentExtractionResponse(
        first_name="John",
        middle_name=None,
        last_name="Doe",
        date_of_birth=date(1990, 1, 1),
        nationality="Sudanese",
        document_number="P123456",
        expiry_date=date(2030, 1, 1),
        address="Khartoum, Sudan",
    )

    assert result.first_name == "John"
    assert result.middle_name is None
    assert result.last_name == "Doe"
    assert result.date_of_birth == date(1990, 1, 1)
    assert result.nationality == "Sudanese"
    assert result.document_number == "P123456"
    assert result.expiry_date == date(2030, 1, 1)
    assert result.address == "Khartoum, Sudan"


def test_document_extraction_response_accepts_ai_json():
    result = DocumentExtractionResponse.model_validate(
        {
            "first_name": "John",
            "last_name": "Doe",
            "date_of_birth": "1990-01-01",
            "nationality": "Sudanese",
            "document_number": "P123456",
            "expiry_date": "2030-01-01",
            "address": "Khartoum, Sudan",
        }
    )

    assert result.first_name == "John"
    assert result.last_name == "Doe"
    assert result.date_of_birth == date(1990, 1, 1)
    assert result.expiry_date == date(2030, 1, 1)


def test_document_extraction_response_allows_missing_fields():
    result = DocumentExtractionResponse(
        first_name="John",
        last_name="Doe",
        document_number="P123456",
    )

    assert result.first_name == "John"
    assert result.last_name == "Doe"
    assert result.document_number == "P123456"
    assert result.date_of_birth is None
    assert result.nationality is None
    assert result.expiry_date is None
    assert result.address is None


def test_document_extraction_response_rejects_invalid_date():
    with pytest.raises(ValidationError):
        DocumentExtractionResponse.model_validate(
            {
                "first_name": "John",
                "last_name": "Doe",
                "date_of_birth": "not-a-date",
            }
        )


def test_document_extraction_response_rejects_unexpected_fields():
    with pytest.raises(ValidationError):
        DocumentExtractionResponse.model_validate(
            {
                "first_name": "John",
                "last_name": "Doe",
                "document_number": "P123456",
                "passport_color": "blue",
            }
        )


def test_extraction_provider_is_abstract():
    with pytest.raises(TypeError):
        ExtractionProvider()


def test_mock_extraction_provider_returns_configured_response():
    document_id = uuid4()

    expected = DocumentExtractionResponse(
        first_name="John",
        last_name="Doe",
        date_of_birth=date(1990, 1, 1),
        nationality="Sudanese",
        document_number="P123456",
        expiry_date=date(2030, 1, 1),
        address="Khartoum, Sudan",
    )

    provider = MockExtractionProvider(response=expected)

    result = provider.extract(
        document_id=document_id,
        ocr_text="John Doe\nPassport Number: P123456",
    )

    assert result is expected


def test_mock_extraction_provider_receives_ocr_text():
    document_id = uuid4()
    ocr_text = "John Doe\nPassport Number: P123456"

    expected = DocumentExtractionResponse(
        first_name="John",
        last_name="Doe",
        document_number="P123456",
    )

    provider = MockExtractionProvider(response=expected)

    provider.extract(
        document_id=document_id,
        ocr_text=ocr_text,
    )

    assert provider.document_ids == [document_id]
    assert provider.ocr_texts == [ocr_text]


def test_mock_extraction_provider_raises_configured_error():
    document_id = uuid4()

    provider = MockExtractionProvider(
        error=ExtractionProviderError("Extraction provider failed."),
    )

    with pytest.raises(
        ExtractionProviderError,
        match="Extraction provider failed.",
    ):
        provider.extract(
            document_id=document_id,
            ocr_text="John Doe",
        )


def test_mock_extraction_provider_requires_response():
    document_id = uuid4()

    provider = MockExtractionProvider()

    with pytest.raises(
        ExtractionProviderError,
        match="Mock extraction provider has no configured response.",
    ):
        provider.extract(
            document_id=document_id,
            ocr_text="John Doe",
        )


def test_extraction_provider_factory_returns_mock_provider():
    provider = get_extraction_provider()

    assert isinstance(provider, MockExtractionProvider)


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------


class FakeExtractionProvider(ExtractionProvider):
    def __init__(
        self,
        response: DocumentExtractionResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
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

        if self.error is not None:
            raise self.error

        if self.response is None:
            raise ExtractionProviderError("Fake provider has no configured response.")

        return self.response


class FailingExtractionProvider(ExtractionProvider):
    def extract(
        self,
        *,
        document_id: uuid.UUID,
        ocr_text: str,
    ) -> DocumentExtractionResponse:
        raise ExtractionProviderError("Extraction provider failed.")


class UnexpectedExtractionProvider(ExtractionProvider):
    def extract(
        self,
        *,
        document_id: uuid.UUID,
        ocr_text: str,
    ) -> DocumentExtractionResponse:
        raise RuntimeError("Unexpected provider failure.")


def create_document() -> MagicMock:
    document = MagicMock(spec=CustomerDocument)
    document.id = uuid.uuid4()

    return document


def create_ocr_result(
    document_id: uuid.UUID,
    extracted_text: str = "John Doe\nPassport Number: P123456",
) -> MagicMock:
    ocr_result = MagicMock(spec=OCRResult)
    ocr_result.id = uuid.uuid4()
    ocr_result.document_id = document_id
    ocr_result.extracted_text = extracted_text
    ocr_result.status = OCRProcessingStatus.COMPLETED

    return ocr_result


def create_extraction_response(
    document_number: str | None = "P123456",
) -> DocumentExtractionResponse:
    return DocumentExtractionResponse(
        first_name="John",
        middle_name=None,
        last_name="Doe",
        date_of_birth=date(1990, 1, 1),
        nationality="Sudanese",
        document_number=document_number,
        expiry_date=date(2030, 1, 1),
        address="Khartoum, Sudan",
    )


def create_extraction_service(
    provider: ExtractionProvider,
) -> tuple[DocumentExtractionService, MagicMock]:
    db = MagicMock()

    service = DocumentExtractionService(
        db=db,
        provider=provider,
    )

    # Make the mocked repository behave like the real repository:
    # repository.create(extraction) returns the same extraction after flush.
    service.repository = MagicMock()
    service.repository.create.side_effect = lambda extraction: extraction

    return service, db


def test_extract_document_sends_ocr_text_to_provider(
    client,
    create_test_user,
    cleanup_test_customers,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="extraction-admin@example.com",
    )

    document = create_document()
    ocr_result = create_ocr_result(document.id)

    provider = FakeExtractionProvider(response=create_extraction_response())

    service, _ = create_extraction_service(provider)

    result = service.extract_document(
        document,
        ocr_result,
        requested_by=admin.id,
        email=admin.email,
    )

    assert provider.document_ids == [document.id]
    assert provider.ocr_texts == [ocr_result.extracted_text]
    assert result.status == ExtractionStatus.COMPLETED


def test_extract_document_stores_extracted_fields(
    client,
    create_test_user,
    cleanup_test_customers,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="extraction-fields@example.com",
    )

    document = create_document()
    ocr_result = create_ocr_result(document.id)

    provider = FakeExtractionProvider(response=create_extraction_response())

    service, _ = create_extraction_service(provider)

    result = service.extract_document(
        document,
        ocr_result,
        requested_by=admin.id,
        email=admin.email,
    )

    assert result.first_name == "John"
    assert result.middle_name is None
    assert result.last_name == "Doe"
    assert result.date_of_birth == date(1990, 1, 1)
    assert result.nationality == "Sudanese"
    assert result.document_number == "P123456"
    assert result.expiry_date == date(2030, 1, 1)
    assert result.address == "Khartoum, Sudan"


def test_extract_document_stores_provider_name(
    client,
    create_test_user,
    cleanup_test_customers,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="extraction-provider-name@example.com",
    )

    document = create_document()
    ocr_result = create_ocr_result(document.id)

    provider = FakeExtractionProvider(response=create_extraction_response())

    service, _ = create_extraction_service(provider)

    result = service.extract_document(
        document,
        ocr_result,
        requested_by=admin.id,
        email=admin.email,
    )

    assert result.provider_name == "FakeExtractionProvider"
    assert result.ocr_result_id == ocr_result.id


def test_extract_document_sets_processing_status_before_provider_call(
    client,
    create_test_user,
    cleanup_test_customers,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="extraction-processing@example.com",
    )

    document = create_document()
    ocr_result = create_ocr_result(document.id)

    provider = FakeExtractionProvider(response=create_extraction_response())

    service, _ = create_extraction_service(provider)

    result = service.extract_document(
        document,
        ocr_result,
        requested_by=admin.id,
        email=admin.email,
    )

    assert result.status == ExtractionStatus.COMPLETED
    service.db.flush.assert_called()


def test_extract_document_creates_extraction_record(
    client,
    create_test_user,
    cleanup_test_customers,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="extraction-record@example.com",
    )

    document = create_document()
    ocr_result = create_ocr_result(document.id)

    provider = FakeExtractionProvider(response=create_extraction_response())

    service, _ = create_extraction_service(provider)

    result = service.extract_document(
        document,
        ocr_result,
        requested_by=admin.id,
        email=admin.email,
    )

    service.repository.create.assert_called_once()

    created_extraction = service.repository.create.call_args.args[0]

    assert isinstance(created_extraction, DocumentExtraction)
    assert created_extraction.document_id == document.id
    assert created_extraction.status == ExtractionStatus.COMPLETED
    assert created_extraction.review_status == (ExtractionReviewStatus.PENDING_REVIEW)
    assert created_extraction.first_name == result.first_name
    assert created_extraction.last_name == result.last_name


def test_extract_document_handles_provider_error(
    client,
    create_test_user,
    cleanup_test_customers,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="extraction-provider-error@example.com",
    )

    document = create_document()
    ocr_result = create_ocr_result(document.id)

    provider = FailingExtractionProvider()

    service, _ = create_extraction_service(provider)

    with pytest.raises(
        ExtractionProviderError,
        match="Extraction provider failed.",
    ):
        service.extract_document(
            document,
            ocr_result,
            requested_by=admin.id,
            email=admin.email,
        )

    service.db.flush.assert_called()

    created_extraction = service.repository.create.call_args.args[0]

    assert created_extraction.status == ExtractionStatus.FAILED
    assert created_extraction.error_message == "Extraction provider failed."


def test_extract_document_handles_unexpected_provider_error(
    client,
    create_test_user,
    cleanup_test_customers,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="extraction-unexpected-error@example.com",
    )

    document = create_document()
    ocr_result = create_ocr_result(document.id)

    provider = UnexpectedExtractionProvider()

    service, _ = create_extraction_service(provider)

    with pytest.raises(
        ExtractionProviderError,
        match="Extraction processing failed.",
    ):
        service.extract_document(
            document,
            ocr_result,
            requested_by=admin.id,
            email=admin.email,
        )

    created_extraction = service.repository.create.call_args.args[0]

    assert created_extraction.status == ExtractionStatus.FAILED
    assert created_extraction.error_message == "Unexpected extraction processing error."


def test_extract_document_handles_empty_provider_response(
    client,
    create_test_user,
    cleanup_test_customers,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="extraction-empty-response@example.com",
    )

    document = create_document()
    ocr_result = create_ocr_result(document.id)

    empty_response = DocumentExtractionResponse()

    provider = FakeExtractionProvider(response=empty_response)

    service, _ = create_extraction_service(provider)

    with pytest.raises(
        ExtractionResponseError,
        match="Extraction provider returned no usable fields.",
    ):
        service.extract_document(
            document,
            ocr_result,
            requested_by=admin.id,
            email=admin.email,
        )

    created_extraction = service.repository.create.call_args.args[0]

    assert created_extraction.status == ExtractionStatus.FAILED
    assert (
        created_extraction.error_message
        == "Extraction provider returned no usable fields."
    )


def test_extract_document_by_id_raises_for_missing_document(
    client,
    create_test_user,
    cleanup_test_customers,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="extraction-missing-document@example.com",
    )

    document_id = uuid.uuid4()

    provider = MockExtractionProvider()

    service = DocumentExtractionService(
        db=MagicMock(),
        provider=provider,
    )

    query = MagicMock()
    query.filter.return_value = query
    query.first.return_value = None

    service.db.query.return_value = query

    with pytest.raises(
        Exception,
        match="Document not found",
    ):
        service.extract_document_by_id(
            document_id,
            requested_by=admin.id,
            email=admin.email,
        )


def test_extract_document_by_id_raises_when_no_completed_ocr_result(
    client,
    create_test_user,
    cleanup_test_customers,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="extraction-no-ocr@example.com",
    )

    document = create_document()

    provider = MockExtractionProvider()

    service = DocumentExtractionService(
        db=MagicMock(),
        provider=provider,
    )

    document_query = MagicMock()
    document_query.filter.return_value = document_query
    document_query.first.return_value = document

    ocr_query = MagicMock()
    ocr_query.filter.return_value = ocr_query
    ocr_query.order_by.return_value = ocr_query
    ocr_query.first.return_value = None

    service.db.query.side_effect = [document_query, ocr_query]

    with pytest.raises(
        Exception,
        match="Document has no completed OCR result available for extraction.",
    ):
        service.extract_document_by_id(
            document.id,
            requested_by=admin.id,
            email=admin.email,
        )


def test_extract_document_by_id_commits_successfully(
    client,
    create_test_user,
    cleanup_test_customers,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="extraction-commit@example.com",
    )

    document = create_document()
    ocr_result = create_ocr_result(document.id)

    provider = FakeExtractionProvider(response=create_extraction_response())

    service, db = create_extraction_service(provider)

    document_query = MagicMock()
    document_query.filter.return_value = document_query
    document_query.first.return_value = document

    ocr_query = MagicMock()
    ocr_query.filter.return_value = ocr_query
    ocr_query.order_by.return_value = ocr_query
    ocr_query.first.return_value = ocr_result

    db.query.side_effect = [document_query, ocr_query]

    result = service.extract_document_by_id(
        document.id,
        requested_by=admin.id,
        email=admin.email,
    )

    assert result.status == ExtractionStatus.COMPLETED
    db.commit.assert_called_once()


def test_extract_document_by_id_commits_failed_result(
    client,
    create_test_user,
    cleanup_test_customers,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="extraction-commit-failed@example.com",
    )

    document = create_document()
    ocr_result = create_ocr_result(document.id)

    provider = FailingExtractionProvider()

    service, db = create_extraction_service(provider)

    document_query = MagicMock()
    document_query.filter.return_value = document_query
    document_query.first.return_value = document

    ocr_query = MagicMock()
    ocr_query.filter.return_value = ocr_query
    ocr_query.order_by.return_value = ocr_query
    ocr_query.first.return_value = ocr_result

    db.query.side_effect = [document_query, ocr_query]

    with pytest.raises(
        ExtractionProviderError,
        match="Extraction provider failed.",
    ):
        service.extract_document_by_id(
            document.id,
            requested_by=admin.id,
            email=admin.email,
        )

    db.commit.assert_called_once()

    created_extraction = service.repository.create.call_args.args[0]

    assert created_extraction.status == ExtractionStatus.FAILED
    assert created_extraction.error_message == "Extraction provider failed."


def test_get_latest_result(
    client,
    create_test_user,
    cleanup_test_customers,
):
    document_id = uuid.uuid4()

    provider = MockExtractionProvider()

    service = DocumentExtractionService(
        db=MagicMock(),
        provider=provider,
    )

    expected_extraction = MagicMock(spec=DocumentExtraction)

    service.repository = MagicMock()
    service.repository.get_latest_by_document.return_value = expected_extraction

    result = service.get_latest_result(document_id)

    assert result is expected_extraction

    service.repository.get_latest_by_document.assert_called_once_with(
        document_id,
    )


def test_get_latest_result_returns_none_when_not_found(
    client,
    create_test_user,
    cleanup_test_customers,
):
    document_id = uuid.uuid4()

    provider = MockExtractionProvider()

    service = DocumentExtractionService(
        db=MagicMock(),
        provider=provider,
    )

    service.repository = MagicMock()
    service.repository.get_latest_by_document.return_value = None

    result = service.get_latest_result(document_id)

    assert result is None


# ---------------------------------------------------------------------------
# API-level tests
# ---------------------------------------------------------------------------


def test_extract_document_api_success(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    extraction_service_override,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="extraction-api-admin@example.com",
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        first_name="Extraction",
        last_name="Customer",
        email="extraction-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

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

    cleanup_test_files(upload_response.json()["data"]["file_reference"])

    assert upload_response.status_code == 201

    document_id = uuid.UUID(upload_response.json()["data"]["id"])

    ocr_result = OCRResult(
        document_id=document_id,
        provider_name="mock",
        request_id=uuid.uuid4(),
        extracted_text="John Doe\nPassport Number: P123456",
        status=OCRProcessingStatus.COMPLETED,
    )

    db_session.add(ocr_result)
    db_session.commit()
    db_session.refresh(ocr_result)

    provider = FakeExtractionProvider(response=create_extraction_response())

    extraction_service_override(provider)

    response = client.post(
        f"/api/v1/documents/{document_id}/extraction",
    )

    assert response.status_code == 201

    body = response.json()

    assert body["success"] is True
    assert body["data"]["document_id"] == str(document_id)
    assert body["data"]["ocr_result_id"] == str(ocr_result.id)
    assert body["data"]["extraction_status"] == ExtractionStatus.COMPLETED.value
    assert body["data"]["review_status"] == ExtractionReviewStatus.PENDING_REVIEW.value
    assert body["data"]["first_name"] == "John"
    assert body["data"]["middle_name"] is None
    assert body["data"]["last_name"] == "Doe"
    assert body["data"]["document_number"] == "P123456"

    stored_extraction = (
        db_session.query(DocumentExtraction)
        .filter(DocumentExtraction.document_id == document_id)
        .first()
    )

    assert stored_extraction is not None
    assert stored_extraction.status == ExtractionStatus.COMPLETED
    assert stored_extraction.ocr_result_id == ocr_result.id

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.resource_type == "document_extraction",
            AuditLog.resource_id == stored_extraction.id,
            AuditLog.event_type == AuditEventType.DOCUMENT_EXTRACTION_COMPLETED,
        )
        .first()
    )

    assert audit_log is not None
    assert audit_log.user_id == admin.id


def test_extract_document_api_persists_failed_result(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    extraction_service_override,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="extraction-api-failure@example.com",
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        first_name="Extraction",
        last_name="Customer",
        email="extraction-customer-2@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

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

    cleanup_test_files(upload_response.json()["data"]["file_reference"])

    assert upload_response.status_code == 201

    document_id = uuid.UUID(upload_response.json()["data"]["id"])

    ocr_result = OCRResult(
        document_id=document_id,
        provider_name="mock",
        request_id=uuid.uuid4(),
        extracted_text="John Doe\nPassport Number: P123456",
        status=OCRProcessingStatus.COMPLETED,
    )

    db_session.add(ocr_result)
    db_session.commit()
    db_session.refresh(ocr_result)

    provider = FailingExtractionProvider()

    extraction_service_override(provider)

    with pytest.raises(
        ExtractionProviderError,
        match="Extraction provider failed.",
    ):
        client.post(
            f"/api/v1/documents/{document_id}/extraction",
        )

    stored_extraction = (
        db_session.query(DocumentExtraction)
        .filter(DocumentExtraction.document_id == document_id)
        .order_by(DocumentExtraction.created_at.desc())
        .first()
    )

    assert stored_extraction is not None
    assert stored_extraction.status == ExtractionStatus.FAILED
    assert stored_extraction.error_message == "Extraction provider failed."


def test_extract_document_api_returns_400_when_no_completed_ocr_result(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    extraction_service_override,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="extraction-api-no-ocr@example.com",
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        first_name="Extraction",
        last_name="Customer",
        email="extraction-customer-3@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

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

    cleanup_test_files(upload_response.json()["data"]["file_reference"])

    assert upload_response.status_code == 201

    document_id = upload_response.json()["data"]["id"]

    provider = FakeExtractionProvider(response=create_extraction_response())

    extraction_service_override(provider)

    response = client.post(
        f"/api/v1/documents/{document_id}/extraction",
    )

    assert response.status_code == 400


def test_extract_document_api_returns_404_for_missing_document(
    client,
    create_test_user,
    cleanup_test_customers,
    extraction_service_override,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="extraction-api-missing@example.com",
    )

    authenticate_client(client, admin)

    provider = FakeExtractionProvider(response=create_extraction_response())

    extraction_service_override(provider)

    document_id = uuid.uuid4()

    response = client.post(
        f"/api/v1/documents/{document_id}/extraction",
    )

    assert response.status_code == 404


def test_extract_document_api_requires_authentication(
    client,
    cleanup_test_customers,
):
    document_id = uuid.uuid4()

    response = client.post(
        f"/api/v1/documents/{document_id}/extraction",
    )

    assert response.status_code == 401


def test_extract_document_api_rejects_non_admin_non_compliance(
    client,
    create_test_user,
    cleanup_test_customers,
):
    auditor = create_test_user(
        role=UserRole.AUDITOR,
        email="extraction-api-auditor@example.com",
    )

    authenticate_client(client, auditor)

    document_id = uuid.uuid4()

    response = client.post(
        f"/api/v1/documents/{document_id}/extraction",
    )

    assert response.status_code == 403


def test_get_document_extraction_api_returns_latest_result(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="extraction-api-get@example.com",
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        first_name="Extraction",
        last_name="Customer",
        email="extraction-customer-4@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

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

    cleanup_test_files(upload_response.json()["data"]["file_reference"])

    assert upload_response.status_code == 201

    document_id = uuid.UUID(upload_response.json()["data"]["id"])

    ocr_result = OCRResult(
        document_id=document_id,
        provider_name="mock",
        request_id=uuid.uuid4(),
        extracted_text="John Doe\nPassport Number: P123456",
        status=OCRProcessingStatus.COMPLETED,
    )

    db_session.add(ocr_result)
    db_session.commit()
    db_session.refresh(ocr_result)

    extraction = DocumentExtraction(
        document_id=document_id,
        ocr_result_id=ocr_result.id,
        provider_name="fake",
        status=ExtractionStatus.COMPLETED,
        first_name="John",
        last_name="Doe",
        document_number="P123456",
    )

    db_session.add(extraction)
    db_session.commit()
    db_session.refresh(extraction)

    response = client.get(
        f"/api/v1/documents/{document_id}/extraction",
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["data"]["id"] == str(extraction.id)
    assert body["data"]["document_id"] == str(document_id)
    assert body["data"]["first_name"] == "John"
    assert body["data"]["last_name"] == "Doe"
    assert body["data"]["extraction_status"] == ExtractionStatus.COMPLETED.value


def test_get_document_extraction_api_returns_404_when_no_result_exists(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    cleanup_test_files,
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="extraction-api-get-none@example.com",
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        first_name="Extraction",
        last_name="Customer",
        email="extraction-customer-5@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

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

    cleanup_test_files(upload_response.json()["data"]["file_reference"])

    assert upload_response.status_code == 201

    document_id = upload_response.json()["data"]["id"]

    response = client.get(
        f"/api/v1/documents/{document_id}/extraction",
    )

    assert response.status_code == 404
