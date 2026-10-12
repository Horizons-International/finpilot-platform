from uuid import UUID

from sqlalchemy.orm import Session

from app.models.document import CustomerDocument
from app.models.document_extraction import DocumentExtraction
from app.models.ocr_result import OCRResult
from app.models.user import User
from app.repositories.tenant_scoped_repository import TenantScopedRepository


class DocumentExtractionRepository(TenantScopedRepository[DocumentExtraction]):
    def __init__(self, db: Session, tenant_id: UUID | None = None) -> None:
        resolved_tenant_id = (
            tenant_id if tenant_id is not None else db.info.get("tenant_id")
        )
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError("A tenant context is required for document extractions.")
        super().__init__(db=db, model=DocumentExtraction, tenant_id=resolved_tenant_id)

    def _validate_relationships(self, extraction: DocumentExtraction) -> None:
        document_exists = (
            self.db.query(CustomerDocument.id)
            .filter(
                CustomerDocument.id == extraction.document_id,
                CustomerDocument.tenant_id == self.tenant_id,
            )
            .first()
        )
        if document_exists is None:
            raise ValueError(
                "The source document does not belong to the current tenant."
            )

        if extraction.ocr_result_id is not None:
            ocr_exists = (
                self.db.query(OCRResult.id)
                .filter(
                    OCRResult.id == extraction.ocr_result_id,
                    OCRResult.tenant_id == self.tenant_id,
                )
                .first()
            )
            if ocr_exists is None:
                raise ValueError(
                    "The OCR result does not belong to the current tenant."
                )

        if extraction.reviewed_by is not None:
            reviewer_exists = (
                self.db.query(User.id)
                .filter(
                    User.id == extraction.reviewed_by,
                    User.tenant_id == self.tenant_id,
                )
                .first()
            )
            if reviewer_exists is None:
                raise ValueError("The reviewer does not belong to the current tenant.")

    def create(self, extraction: DocumentExtraction) -> DocumentExtraction:
        self._validate_relationships(extraction)
        return super().create(extraction)

    def update(self, extraction: DocumentExtraction) -> DocumentExtraction:
        self._validate_relationships(extraction)
        return super().update(extraction)

    def get_latest_by_document(self, document_id: UUID) -> DocumentExtraction | None:
        return (
            self.query()
            .filter(DocumentExtraction.document_id == document_id)
            .order_by(DocumentExtraction.created_at.desc())
            .first()
        )

    def get_by_ocr_result(self, ocr_result_id: UUID) -> DocumentExtraction | None:
        return (
            self.query()
            .filter(DocumentExtraction.ocr_result_id == ocr_result_id)
            .first()
        )
