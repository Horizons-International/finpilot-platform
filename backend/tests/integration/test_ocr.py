import uuid
from io import BytesIO
from unittest.mock import MagicMock

import pytest

from app.models.audit_log import AuditLog
from app.models.document import CustomerDocument
from app.models.ocr_result import OCRResult
from app.models.verification_document_type import VerificationDocumentType
from app.ocr.exceptions import (
    OCRConfigurationError,
    OCRProviderError,
    OCRResponseError,
)
from app.ocr.providers.base import OCRProvider
from app.ocr.providers.factory import get_ocr_provider
from app.ocr.providers.mock import MockOCRProvider
from app.ocr.schemas.requests import OCRRequest
from app.ocr.schemas.responses import OCRResponse
from app.ocr.services.ocr_service import OCRService
from app.utils.enums import AuditEventType, OCRProcessingStatus, UserRole


class FakeOCRProvider(OCRProvider):
    def __init__(
        self,
        response: OCRResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.requests: list[OCRRequest] = []

    def process(self, request: OCRRequest) -> OCRResponse:
        self.requests.append(request)

        if self.error is not None:
            raise self.error

        if self.response is None:
            raise OCRProviderError("Fake provider has no configured response.")

        return self.response


class FailingOCRProvider(OCRProvider):
    def process(self, request: OCRRequest) -> OCRResponse:
        raise OCRProviderError("OCR provider failed.")


class UnexpectedOCRProvider(OCRProvider):
    def process(self, request: OCRRequest) -> OCRResponse:
        raise RuntimeError("Unexpected provider failure.")


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


def create_document() -> MagicMock:
    document = MagicMock(spec=CustomerDocument)

    document.id = uuid.uuid4()
    document.file_reference = "uploads/test-document.pdf"
    document.file_name = "test-document.pdf"
    document.file_type = "application/pdf"

    return document


def create_response(
    document_id: uuid.UUID,
    extracted_text: str = "John Doe\nPassport Number: P123456",
    status: str = OCRProcessingStatus.COMPLETED.value,
) -> OCRResponse:
    return OCRResponse(
        provider_name="fake",
        document_id=document_id,
        extracted_text=extracted_text,
        processing_status=status,
        request_id=uuid.uuid4(),
    )


def create_service(
    provider: OCRProvider,
) -> tuple[OCRService, MagicMock]:
    db = MagicMock()

    service = OCRService(
        db=db,
        provider=provider,
    )

    # Make the mocked repository behave like the real repository:
    # repository.create(result) returns the same result after flush.
    service.repository = MagicMock()
    service.repository.create.side_effect = lambda result: result

    return service, db


def test_process_document_sends_request_to_provider(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin@example.com",
    )

    document = create_document()
    response = create_response(document.id)

    provider = FakeOCRProvider(response=response)

    service, _ = create_service(provider)

    result = service.process_document(
        document,
        requested_by=admin.id,
    )

    assert len(provider.requests) == 1

    request = provider.requests[0]

    assert request.document_id == document.id
    assert request.file_reference == document.file_reference
    assert request.file_name == document.file_name
    assert request.file_type == document.file_type

    assert result.status == OCRProcessingStatus.COMPLETED


def test_process_document_returns_extracted_text(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin@example.com",
    )

    document = create_document()

    response = create_response(
        document.id,
        extracted_text="John Doe\nDOB: 1990-01-01",
    )

    provider = FakeOCRProvider(response=response)

    service, _ = create_service(provider)

    result = service.process_document(
        document,
        requested_by=admin.id,
    )

    assert result.status == OCRProcessingStatus.COMPLETED
    assert result.extracted_text == "John Doe\nDOB: 1990-01-01"


def test_process_document_stores_provider_information(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin@example.com",
    )

    document = create_document()

    response = OCRResponse(
        provider_name="test-provider",
        document_id=document.id,
        extracted_text="Extracted text",
        processing_status=OCRProcessingStatus.COMPLETED.value,
        request_id=uuid.uuid4(),
    )

    provider = FakeOCRProvider(response=response)

    service, _ = create_service(provider)

    result = service.process_document(
        document,
        requested_by=admin.id,
    )

    assert result.provider_name == "test-provider"
    assert result.request_id == response.request_id


def test_process_document_sets_processing_status_before_provider_call(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin@example.com",
    )

    document = create_document()
    response = create_response(document.id)

    provider = FakeOCRProvider(response=response)

    service, _ = create_service(provider)

    result = service.process_document(
        document,
        requested_by=admin.id,
    )

    assert result.status == OCRProcessingStatus.COMPLETED
    service.db.flush.assert_called()


def test_process_document_creates_ocr_result(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin@example.com",
    )

    document = create_document()
    response = create_response(document.id)

    provider = FakeOCRProvider(response=response)

    service, _ = create_service(provider)

    result = service.process_document(
        document,
        requested_by=admin.id,
    )

    service.repository.create.assert_called_once()

    created_result = service.repository.create.call_args.args[0]

    assert isinstance(created_result, OCRResult)
    assert created_result.document_id == document.id
    assert created_result.status == OCRProcessingStatus.COMPLETED
    assert created_result.extracted_text == result.extracted_text


def test_process_document_handles_provider_error(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin@example.com",
    )

    document = create_document()

    provider = FailingOCRProvider()

    service, _ = create_service(provider)

    with pytest.raises(
        OCRProviderError,
        match="OCR provider failed.",
    ):
        service.process_document(
            document,
            requested_by=admin.id,
        )

    service.db.flush.assert_called()

    created_result = service.repository.create.call_args.args[0]

    assert created_result.status == OCRProcessingStatus.FAILED
    assert created_result.error_message == "OCR provider failed."


def test_process_document_handles_unexpected_provider_error(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin@example.com",
    )

    document = create_document()

    provider = UnexpectedOCRProvider()

    service, _ = create_service(provider)

    with pytest.raises(
        OCRProviderError,
        match="OCR processing failed.",
    ):
        service.process_document(
            document,
            requested_by=admin.id,
        )

    created_result = service.repository.create.call_args.args[0]

    assert created_result.status == OCRProcessingStatus.FAILED
    assert created_result.error_message == "Unexpected OCR processing error."


def test_process_document_handles_empty_extracted_text(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin@example.com",
    )

    document = create_document()

    response = create_response(
        document.id,
        extracted_text="",
    )

    provider = FakeOCRProvider(response=response)

    service, _ = create_service(provider)

    with pytest.raises(
        OCRResponseError,
        match="OCR provider returned empty extracted text.",
    ):
        service.process_document(
            document,
            requested_by=admin.id,
        )

    created_result = service.repository.create.call_args.args[0]

    assert created_result.status == OCRProcessingStatus.FAILED
    assert created_result.error_message == "OCR provider returned empty extracted text."


def test_process_document_handles_incomplete_provider_status(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin@example.com",
    )

    document = create_document()

    response = create_response(
        document.id,
        status=OCRProcessingStatus.PROCESSING.value,
    )

    provider = FakeOCRProvider(response=response)

    service, _ = create_service(provider)

    with pytest.raises(
        OCRResponseError,
        match="OCR provider did not complete processing.",
    ):
        service.process_document(
            document,
            requested_by=admin.id,
        )

    created_result = service.repository.create.call_args.args[0]

    assert created_result.status == OCRProcessingStatus.FAILED
    assert created_result.error_message == "OCR provider did not complete processing."


def test_process_document_rejects_provider_response_for_wrong_document(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin@example.com",
    )

    document = create_document()

    response = create_response(
        uuid.uuid4(),
        extracted_text="Wrong document response",
    )

    provider = FakeOCRProvider(response=response)

    service, _ = create_service(provider)

    with pytest.raises(
        OCRResponseError,
        match="OCR provider returned a response for a different document.",
    ):
        service.process_document(
            document,
            requested_by=admin.id,
        )

    created_result = service.repository.create.call_args.args[0]

    assert created_result.status == OCRProcessingStatus.FAILED
    assert (
        created_result.error_message
        == "OCR provider returned a response for a different document."
    )


def test_process_document_by_id_raises_for_missing_document(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin@example.com",
    )

    document_id = uuid.uuid4()

    provider = MockOCRProvider()

    service = OCRService(
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
        service.process_document_by_id(
            document_id,
            requested_by=admin.id,
        )


def test_process_document_by_id_commits_successfully(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin@example.com",
    )

    document = create_document()

    response = create_response(document.id)

    provider = FakeOCRProvider(response=response)

    service, db = create_service(provider)

    query = MagicMock()
    query.filter.return_value = query
    query.first.return_value = document

    db.query.return_value = query

    result = service.process_document_by_id(
        document.id,
        requested_by=admin.id,
    )

    assert result.status == OCRProcessingStatus.COMPLETED
    db.commit.assert_called_once()


def test_process_document_by_id_commits_failed_result(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin@example.com",
    )

    document = create_document()

    provider = FailingOCRProvider()

    service, db = create_service(provider)

    query = MagicMock()
    query.filter.return_value = query
    query.first.return_value = document

    db.query.return_value = query

    with pytest.raises(
        OCRProviderError,
        match="OCR provider failed.",
    ):
        service.process_document_by_id(
            document.id,
            requested_by=admin.id,
        )

    db.commit.assert_called_once()

    created_result = service.repository.create.call_args.args[0]

    assert created_result.status == OCRProcessingStatus.FAILED
    assert created_result.error_message == "OCR provider failed."


def test_get_latest_result(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin@example.com",
    )

    document_id = uuid.uuid4()

    provider = MockOCRProvider()

    service = OCRService(
        db=MagicMock(),
        provider=provider,
    )

    expected_result = MagicMock(spec=OCRResult)

    service.repository = MagicMock()
    service.repository.get_latest_by_document.return_value = expected_result

    result = service.get_latest_result(document_id)

    assert result is expected_result

    service.repository.get_latest_by_document.assert_called_once_with(
        document_id,
    )


def test_get_latest_result_returns_none_when_not_found(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin@example.com",
    )

    document_id = uuid.uuid4()

    provider = MockOCRProvider()

    service = OCRService(
        db=MagicMock(),
        provider=provider,
    )

    service.repository = MagicMock()
    service.repository.get_latest_by_document.return_value = None

    result = service.get_latest_result(document_id)

    assert result is None


def test_mock_ocr_provider_returns_completed_response():
    document_id = uuid.uuid4()

    request = OCRRequest(
        document_id=document_id,
        file_reference="uploads/document.pdf",
        file_name="document.pdf",
        file_type="application/pdf",
    )

    provider = MockOCRProvider()

    response = provider.process(request)

    assert response.provider_name == "mock"
    assert response.document_id == document_id
    assert response.processing_status == (OCRProcessingStatus.COMPLETED.value)
    assert response.extracted_text
    assert response.request_id is not None


def test_mock_ocr_provider_requires_file_reference():
    document_id = uuid.uuid4()

    request = OCRRequest(
        document_id=document_id,
        file_reference="",
        file_name="document.pdf",
        file_type="application/pdf",
    )

    provider = MockOCRProvider()

    with pytest.raises(
        OCRProviderError,
        match="Document file reference is required.",
    ):
        provider.process(request)


def test_ocr_provider_factory_returns_mock_provider(monkeypatch):
    monkeypatch.setattr(
        "app.ocr.providers.factory.settings.OCR_PROVIDER",
        "mock",
    )

    provider = get_ocr_provider()

    assert isinstance(provider, MockOCRProvider)


def test_ocr_provider_factory_rejects_unsupported_provider(monkeypatch):
    monkeypatch.setattr(
        "app.ocr.providers.factory.settings.OCR_PROVIDER",
        "unsupported",
    )

    with pytest.raises(
        OCRConfigurationError,
        match="Unsupported OCR provider",
    ):
        get_ocr_provider()


def test_process_document_ocr_api_success(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    ocr_service_override,
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="ocr-admin@example.com",
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
        filename="identity-document.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 identity document",
    )

    assert response.status_code == 201

    document_id = uuid.UUID(response.json()["data"]["id"])

    provider = FakeOCRProvider(
        response=create_response(document_id),
    )

    ocr_service_override(provider)

    response = client.post(
        f"/api/v1/documents/{document_id}/ocr",
    )

    assert response.status_code == 201

    body = response.json()

    assert body["success"] is True
    assert body["data"]["document_id"] == str(document_id)
    assert body["data"]["provider_name"] == "fake"
    assert body["data"]["extracted_text"] == ("John Doe\nPassport Number: P123456")

    assert len(provider.requests) == 1

    stored_result = (
        db_session.query(OCRResult).filter(OCRResult.document_id == document_id).first()
    )

    assert stored_result is not None
    assert stored_result.status == OCRProcessingStatus.COMPLETED
    assert stored_result.extracted_text == ("John Doe\nPassport Number: P123456")


def test_process_document_ocr_api_uses_authenticated_requester(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    ocr_service_override,
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="ocr-requester@example.com",
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

    document_id = upload_response.json()["data"]["id"]

    provider = FakeOCRProvider(
        response=create_response(uuid.UUID(document_id)),
    )

    ocr_service_override(provider)

    response = client.post(
        f"/api/v1/documents/{document_id}/ocr",
    )

    assert response.status_code == 201

    body = response.json()

    assert body["success"] is True
    assert body["data"]["document_id"] == document_id
    assert body["data"]["status"] == OCRProcessingStatus.COMPLETED.value

    ocr_result_id = body["data"]["id"]

    stored_result = (
        db_session.query(OCRResult)
        .filter(OCRResult.id == uuid.UUID(ocr_result_id))
        .first()
    )

    assert stored_result is not None
    assert stored_result.document_id == uuid.UUID(document_id)

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.resource_type == "ocr_result",
            AuditLog.resource_id == stored_result.id,
            AuditLog.event_type == AuditEventType.OCR_COMPLETED,
        )
        .first()
    )

    assert audit_log is not None
    assert audit_log.user_id == admin.id


def test_process_document_ocr_api_persists_failed_result(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
    ocr_service_override,
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="ocr-failure@example.com",
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
        filename="identity-document.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 identity document",
    )

    assert response.status_code == 201

    document_id = response.json()["data"]["id"]

    provider = FailingOCRProvider()

    service = ocr_service_override(provider)

    assert service.provider is provider

    with pytest.raises(
        OCRProviderError,
        match="OCR provider failed.",
    ):
        client.post(
            f"/api/v1/documents/{document_id}/ocr",
        )

    stored_result = (
        db_session.query(OCRResult)
        .filter(OCRResult.document_id == document_id)
        .order_by(OCRResult.created_at.desc())
        .first()
    )

    assert stored_result is not None
    assert stored_result.status == OCRProcessingStatus.FAILED
    assert stored_result.error_message == "OCR provider failed."


def test_process_document_ocr_api_returns_404_for_missing_document(
    client,
    create_test_user,
    cleanup_test_customers,
    ocr_service_override,
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="ocr-missing@example.com",
    )

    authenticate_client(client, admin)

    provider = FakeOCRProvider(
        response=create_response(uuid.uuid4()),
    )

    ocr_service_override(provider)

    document_id = uuid.uuid4()

    response = client.post(
        f"/api/v1/documents/{document_id}/ocr",
    )

    assert response.status_code == 404


def test_process_document_ocr_api_requires_authentication(
    client,
    cleanup_test_customers,
):
    document_id = uuid.uuid4()

    response = client.post(
        f"/api/v1/documents/{document_id}/ocr",
    )

    assert response.status_code == 401


def test_process_document_ocr_api_rejects_non_admin(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, auditor = create_test_user(
        role=UserRole.AUDITOR,
        email="ocr-auditor@example.com",
    )

    authenticate_client(client, auditor)

    document_id = uuid.uuid4()

    response = client.post(
        f"/api/v1/documents/{document_id}/ocr",
    )

    assert response.status_code == 403


def test_get_document_ocr_api_returns_latest_result(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="ocr-get@example.com",
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
        filename="identity-document.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 identity document",
    )

    assert response.status_code == 201

    document_id = response.json()["data"]["id"]

    result = OCRResult(
        document_id=document_id,
        provider_name="fake",
        request_id=uuid.uuid4(),
        extracted_text="Latest OCR text",
        status=OCRProcessingStatus.COMPLETED,
    )

    db_session.add(result)
    db_session.commit()
    db_session.refresh(result)

    response = client.get(
        f"/api/v1/documents/{document_id}/ocr",
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["data"]["id"] == str(result.id)
    assert body["data"]["document_id"] == str(document_id)
    assert body["data"]["extracted_text"] == "Latest OCR text"
    assert body["data"]["status"] == OCRProcessingStatus.COMPLETED.value


def test_get_document_ocr_api_returns_404_when_no_result_exists(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="ocr-no-result@example.com",
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
        filename="identity-document.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 identity document",
    )

    assert response.status_code == 201

    document_id = response.json()["data"]["id"]

    response = client.get(
        f"/api/v1/documents/{document_id}/ocr",
    )

    assert response.status_code == 404
