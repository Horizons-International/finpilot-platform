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
from app.services.tenant_access_audit import deny_tenant_access
from app.utils.enums import AuditEventType, OCRProcessingStatus

logger = get_logger(__name__)


class OCRService:
    def __init__(
        self,
        db: Session,
        provider: OCRProvider,
        *,
        tenant_id: UUID,
        actor_user_id: UUID | None = None,
        actor_email: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_user_id = actor_user_id
        self.actor_email = actor_email
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.provider = provider
        self.repository = OCRRepository(
            db=db,
            tenant_id=self.tenant_id,
        )
        self.audit_service = AuditService(db)

    def process_document(
        self,
        document: CustomerDocument,
        requested_by: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> OCRResult:
        logger.info(
            "OCR request started: provider=%s document_id=%s",
            self.provider.__class__.__name__,
            document.id,
        )

        result = OCRResult(
            tenant_id=self.tenant_id,
            document_id=document.id,
            provider_name=self.provider.__class__.__name__,
            status=OCRProcessingStatus.SUBMITTED,
        )

        self.repository.create(result)

        self.audit_service.log_event(
            user_id=requested_by,
            event_type=AuditEventType.OCR_REQUESTED,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
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
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
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
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
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
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
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
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
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
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> OCRResult:
        document = (
            self.db.query(CustomerDocument)
            .filter(
                CustomerDocument.id == document_id,
                CustomerDocument.tenant_id == self.tenant_id,
            )
            .first()
        )

        if document is None:
            deny_tenant_access(
                self.db,
                user_id=self.actor_user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="customer_document",
                resource_id=document_id,
                resource_name="Document",
            )

        try:
            result = self.process_document(
                document,
                requested_by=requested_by,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            self.db.commit()

            return result

        except Exception:
            self.db.commit()
            raise

    def get_latest_result(
        self,
        document_id: UUID,
    ) -> OCRResult | None:
        document = (
            self.db.query(CustomerDocument)
            .filter(
                CustomerDocument.id == document_id,
                CustomerDocument.tenant_id == self.tenant_id,
            )
            .first()
        )

        if document is None:
            deny_tenant_access(
                self.db,
                user_id=self.actor_user_id,
                email=self.actor_email,
                ip_address=self.ip_address,
                user_agent=self.user_agent,
                resource_type="customer_document",
                resource_id=document_id,
                resource_name="Document",
            )

        return self.repository.get_latest_by_document(document_id)
