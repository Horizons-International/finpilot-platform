from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.extraction.exceptions import ExtractionProviderError, ExtractionResponseError
from app.extraction.providers.base import ExtractionProvider
from app.models.document import CustomerDocument
from app.models.document_extraction import DocumentExtraction
from app.models.ocr_result import OCRResult
from app.repositories.document_extraction_repository import (
    DocumentExtractionRepository,
)
from app.services.audit_service import AuditService
from app.utils.enums import AuditEventType, ExtractionStatus, OCRProcessingStatus
from app.utils.errors import bad_request, not_found

logger = get_logger(__name__)


class DocumentExtractionService:
    def __init__(
        self,
        db: Session,
        provider: ExtractionProvider,
    ) -> None:
        self.db = db
        self.provider = provider
        self.repository = DocumentExtractionRepository(db)
        self.audit_service = AuditService(db)

    def extract_document(
        self,
        document: CustomerDocument,
        ocr_result: OCRResult,
        requested_by: UUID,
    ) -> DocumentExtraction:
        logger.info(
            "Extraction request started: provider=%s document_id=%s ocr_result_id=%s",
            self.provider.__class__.__name__,
            document.id,
            ocr_result.id,
        )

        extraction = DocumentExtraction(
            document_id=document.id,
            ocr_result_id=ocr_result.id,
            provider_name=self.provider.__class__.__name__,
            status=ExtractionStatus.SUBMITTED,
        )

        self.repository.create(extraction)

        self.audit_service.log_event(
            user_id=requested_by,
            event_type=AuditEventType.DOCUMENT_EXTRACTION_REQUESTED,
            resource_type="document_extraction",
            resource_id=extraction.id,
        )

        try:
            extraction.status = ExtractionStatus.PROCESSING
            self.db.flush()

            if not ocr_result.extracted_text:
                raise ExtractionResponseError(
                    "OCR result does not contain extracted text."
                )

            response = self.provider.extract(
                document_id=document.id,
                ocr_text=ocr_result.extracted_text,
            )

            if not any(
                (
                    response.full_name,
                    response.date_of_birth,
                    response.nationality,
                    response.document_number,
                    response.expiry_date,
                    response.address,
                )
            ):
                raise ExtractionResponseError(
                    "Extraction provider returned no usable fields."
                )

            extraction.full_name = response.full_name
            extraction.date_of_birth = response.date_of_birth
            extraction.nationality = response.nationality
            extraction.document_number = response.document_number
            extraction.expiry_date = response.expiry_date
            extraction.address = response.address
            extraction.status = ExtractionStatus.COMPLETED
            extraction.error_message = None

            self.db.flush()

            self.audit_service.log_event(
                user_id=requested_by,
                event_type=AuditEventType.DOCUMENT_EXTRACTION_COMPLETED,
                resource_type="document_extraction",
                resource_id=extraction.id,
            )

            logger.info(
                "Extraction request completed: provider=%s document_id=%s",
                extraction.provider_name,
                document.id,
            )

            return extraction

        except ExtractionProviderError as exc:
            extraction.status = ExtractionStatus.FAILED
            extraction.error_message = str(exc)

            self.db.flush()

            self.audit_service.log_event(
                user_id=requested_by,
                event_type=AuditEventType.DOCUMENT_EXTRACTION_FAILED,
                resource_type="document_extraction",
                resource_id=extraction.id,
            )

            logger.exception(
                "Extraction provider failed: document_id=%s",
                document.id,
            )

            raise

        except ExtractionResponseError as exc:
            extraction.status = ExtractionStatus.FAILED
            extraction.error_message = str(exc)

            self.db.flush()

            self.audit_service.log_event(
                user_id=requested_by,
                event_type=AuditEventType.DOCUMENT_EXTRACTION_FAILED,
                resource_type="document_extraction",
                resource_id=extraction.id,
            )

            logger.exception(
                "Extraction provider returned invalid response: document_id=%s",
                document.id,
            )

            raise

        except Exception as exc:
            extraction.status = ExtractionStatus.FAILED
            extraction.error_message = "Unexpected extraction processing error."

            self.db.flush()

            self.audit_service.log_event(
                user_id=requested_by,
                event_type=AuditEventType.DOCUMENT_EXTRACTION_FAILED,
                resource_type="document_extraction",
                resource_id=extraction.id,
            )

            logger.exception(
                "Unexpected extraction processing error: document_id=%s",
                document.id,
            )

            raise ExtractionProviderError("Extraction processing failed.") from exc

    def extract_document_by_id(
        self,
        document_id: UUID,
        requested_by: UUID,
    ) -> DocumentExtraction:
        document = (
            self.db.query(CustomerDocument)
            .filter(CustomerDocument.id == document_id)
            .first()
        )

        if document is None:
            raise not_found("Document")

        ocr_result = (
            self.db.query(OCRResult)
            .filter(
                OCRResult.document_id == document_id,
                OCRResult.status == OCRProcessingStatus.COMPLETED,
            )
            .order_by(OCRResult.created_at.desc())
            .first()
        )

        if ocr_result is None:
            raise bad_request(
                "Document has no completed OCR result available for extraction."
            )

        try:
            extraction = self.extract_document(
                document,
                ocr_result,
                requested_by=requested_by,
            )
            self.db.commit()

            return extraction

        except Exception:
            self.db.commit()
            raise

    def get_latest_result(
        self,
        document_id: UUID,
    ) -> DocumentExtraction | None:
        return self.repository.get_latest_by_document(document_id)
