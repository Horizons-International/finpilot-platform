from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.document import CustomerDocument
from app.models.document_extraction import DocumentExtraction
from app.models.ocr_result import OCRResult
from app.schemas.customer import CustomerUpdate
from app.schemas.extraction_review import ExtractionReviewUpdate
from app.services.audit_service import AuditService
from app.services.customer_service import CustomerService
from app.services.document_extraction_review_log_service import (
    DocumentExtractionReviewLogService,
)
from app.utils.enums import (
    AuditEventType,
    ExtractionReviewStatus,
    ExtractionStatus,
    OCRProcessingStatus,
)
from app.utils.errors import bad_request, not_found


class DocumentReviewService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit_service = AuditService(db)
        self.review_log_service = DocumentExtractionReviewLogService(db)
        self.customer_service = CustomerService(db)

    def get_review(
        self,
        document_id: UUID,
    ) -> tuple[
        CustomerDocument,
        OCRResult,
        DocumentExtraction,
        Customer,
    ]:
        document = (
            self.db.query(CustomerDocument)
            .filter(
                CustomerDocument.id == document_id,
            )
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
            .order_by(
                OCRResult.created_at.desc(),
            )
            .first()
        )

        if ocr_result is None:
            raise bad_request(
                "Document has no completed OCR result available for review."
            )

        extraction = (
            self.db.query(DocumentExtraction)
            .filter(
                DocumentExtraction.document_id == document_id,
                DocumentExtraction.ocr_result_id == ocr_result.id,
            )
            .order_by(
                DocumentExtraction.created_at.desc(),
            )
            .first()
        )

        if extraction is None:
            raise bad_request("Document has no extraction result available for review.")

        if extraction.status != ExtractionStatus.COMPLETED:
            raise bad_request("Document extraction is not completed.")

        customer = (
            self.db.query(Customer)
            .filter(
                Customer.id == document.customer_id,
            )
            .first()
        )

        if customer is None:
            raise not_found("Customer")

        return (
            document,
            ocr_result,
            extraction,
            customer,
        )

    def update_extraction(
        self,
        *,
        document_id: UUID,
        reviewer_id: UUID,
        data: ExtractionReviewUpdate,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> DocumentExtraction:
        (
            _document,
            _ocr_result,
            extraction,
            _customer,
        ) = self.get_review(document_id)

        self._ensure_pending(extraction)

        changes = data.model_dump(
            exclude_unset=True,
        )

        if not changes:
            raise bad_request("No extraction fields were provided for update.")

        for field_name, new_value in changes.items():
            old_value = getattr(
                extraction,
                field_name,
            )

            if old_value == new_value:
                continue

            setattr(
                extraction,
                field_name,
                new_value,
            )

            self.review_log_service.log_change(
                extraction_id=extraction.id,
                reviewer_id=reviewer_id,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
            )

        self.db.flush()

        self.audit_service.log_event(
            user_id=reviewer_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            event_type=AuditEventType.DOCUMENT_EXTRACTION_REVIEW_UPDATED,
            resource_type="document_extraction",
            resource_id=extraction.id,
        )

        self.db.commit()
        self.db.refresh(extraction)

        return extraction

    def approve(
        self,
        *,
        document_id: UUID,
        reviewer_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> DocumentExtraction:
        (
            _document,
            _ocr_result,
            extraction,
            customer,
        ) = self.get_review(document_id)

        self._ensure_pending(extraction)

        self._validate_for_approval(extraction)

        update_data = {}

        for field_name in (
            "first_name",
            "middle_name",
            "last_name",
            "date_of_birth",
            "nationality",
        ):
            value = getattr(extraction, field_name)

            if value is not None:
                update_data[field_name] = value

        customer_update = CustomerUpdate(**update_data)

        self.customer_service.update_customer(
            customer.id,
            customer_update,
            updated_by=reviewer_id,
            commit=False,
        )

        extraction.review_status = ExtractionReviewStatus.APPROVED
        extraction.reviewed_by = reviewer_id
        extraction.reviewed_at = datetime.now(timezone.utc)
        extraction.rejection_reason = None

        self.db.flush()

        self.audit_service.log_event(
            user_id=reviewer_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            event_type=AuditEventType.DOCUMENT_EXTRACTION_REVIEW_APPROVED,
            resource_type="document_extraction",
            resource_id=extraction.id,
        )

        self.db.commit()
        self.db.refresh(extraction)

        return extraction

    def reject(
        self,
        *,
        document_id: UUID,
        reviewer_id: UUID,
        reason: str,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> DocumentExtraction:
        (
            _document,
            _ocr_result,
            extraction,
            _customer,
        ) = self.get_review(document_id)

        self._ensure_pending(extraction)

        normalized_reason = reason.strip()

        if not normalized_reason:
            raise bad_request("Rejection reason is required.")

        extraction.review_status = ExtractionReviewStatus.REJECTED
        extraction.reviewed_by = reviewer_id
        extraction.reviewed_at = datetime.now(timezone.utc)
        extraction.rejection_reason = normalized_reason

        self.db.flush()

        self.audit_service.log_event(
            user_id=reviewer_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            event_type=AuditEventType.DOCUMENT_EXTRACTION_REVIEW_REJECTED,
            resource_type="document_extraction",
            resource_id=extraction.id,
        )

        self.db.commit()
        self.db.refresh(extraction)

        return extraction

    @staticmethod
    def _ensure_pending(
        extraction: DocumentExtraction,
    ) -> None:
        if extraction.review_status != ExtractionReviewStatus.PENDING_REVIEW:
            raise bad_request("Document extraction has already been reviewed.")

    @staticmethod
    def _validate_for_approval(
        extraction: DocumentExtraction,
    ) -> None:
        if not any(
            (
                extraction.first_name,
                extraction.middle_name,
                extraction.last_name,
                extraction.date_of_birth,
                extraction.nationality,
                extraction.document_number,
                extraction.expiry_date,
                extraction.address,
            )
        ):
            raise bad_request("Document extraction contains no usable fields.")
