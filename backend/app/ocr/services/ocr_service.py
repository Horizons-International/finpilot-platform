from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.models.document import CustomerDocument
from app.models.ocr_result import OCRResult
from app.ocr.exceptions import OCRProviderError, OCRResponseError
from app.ocr.providers.base import OCRProvider
from app.ocr.schemas.requests import OCRRequest
from app.repositories.ocr_repository import OCRRepository
from app.services.audit_service import AuditService
from app.utils.enums import AuditEventType, OCRProcessingStatus
from app.utils.errors import not_found

logger = get_logger(__name__)


class OCRService:
    def __init__(
        self,
        db: Session,
        provider: OCRProvider,
    ) -> None:
        self.db = db
        self.provider = provider
        self.repository = OCRRepository(db)
        self.audit_service = AuditService(db)

    def process_document(
        self,
        document: CustomerDocument,
        requested_by: UUID,
    ) -> OCRResult:
        logger.info(
            "OCR request started: provider=%s document_id=%s",
            self.provider.__class__.__name__,
            document.id,
        )

        result = OCRResult(
            document_id=document.id,
            provider_name=self.provider.__class__.__name__,
            status=OCRProcessingStatus.SUBMITTED,
        )

        self.repository.create(result)

        self.audit_service.log_event(
            user_id=requested_by,
            event_type=AuditEventType.OCR_REQUESTED,
            resource_type="ocr_result",
            resource_id=result.id,
        )

        try:
            result.status = OCRProcessingStatus.PROCESSING
            self.db.flush()

            request = OCRRequest(
                document_id=document.id,
                file_reference=document.file_reference,
                file_name=document.file_name,
                file_type=document.file_type,
            )

            response = self.provider.process(request)

            if response.document_id != document.id:
                raise OCRResponseError(
                    "OCR provider returned a response for a different document."
                )

            if response.processing_status != (OCRProcessingStatus.COMPLETED.value):
                raise OCRResponseError("OCR provider did not complete processing.")

            if not response.extracted_text:
                raise OCRResponseError("OCR provider returned empty extracted text.")

            result.provider_name = response.provider_name
            result.request_id = response.request_id
            result.status = OCRProcessingStatus.COMPLETED
            result.extracted_text = response.extracted_text
            result.error_message = None

            self.db.flush()

            self.audit_service.log_event(
                user_id=requested_by,
                event_type=AuditEventType.OCR_COMPLETED,
                resource_type="ocr_result",
                resource_id=result.id,
            )

            logger.info(
                "OCR request completed: provider=%s document_id=%s request_id=%s",
                response.provider_name,
                document.id,
                response.request_id,
            )

            return result

        except OCRProviderError as exc:
            result.status = OCRProcessingStatus.FAILED
            result.error_message = str(exc)

            self.db.flush()

            self.audit_service.log_event(
                user_id=requested_by,
                event_type=AuditEventType.OCR_FAILED,
                resource_type="ocr_result",
                resource_id=result.id,
            )

            logger.exception(
                "OCR provider failed: document_id=%s",
                document.id,
            )

            raise

        except OCRResponseError as exc:
            result.status = OCRProcessingStatus.FAILED
            result.error_message = str(exc)

            self.db.flush()

            self.audit_service.log_event(
                user_id=requested_by,
                event_type=AuditEventType.OCR_FAILED,
                resource_type="ocr_result",
                resource_id=result.id,
            )

            logger.exception(
                "OCR provider returned invalid response: document_id=%s",
                document.id,
            )

            raise

        except Exception as exc:
            result.status = OCRProcessingStatus.FAILED
            result.error_message = "Unexpected OCR processing error."

            self.db.flush()

            self.audit_service.log_event(
                user_id=requested_by,
                event_type=AuditEventType.OCR_FAILED,
                resource_type="ocr_result",
                resource_id=result.id,
            )

            logger.exception(
                "Unexpected OCR processing error: document_id=%s",
                document.id,
            )

            raise OCRProviderError("OCR processing failed.") from exc

    def process_document_by_id(
        self,
        document_id: UUID,
        requested_by: UUID,
    ) -> OCRResult:
        document = (
            self.db.query(CustomerDocument)
            .filter(CustomerDocument.id == document_id)
            .first()
        )

        if document is None:
            raise not_found("Document")

        try:
            result = self.process_document(document, requested_by=requested_by)
            self.db.commit()

            return result

        except Exception:
            self.db.commit()
            raise

    def get_latest_result(
        self,
        document_id: UUID,
    ) -> OCRResult | None:
        return self.repository.get_latest_by_document(document_id)
