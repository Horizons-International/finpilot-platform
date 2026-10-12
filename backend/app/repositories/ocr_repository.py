from uuid import UUID

from sqlalchemy.orm import Session

from app.models.document import CustomerDocument
from app.models.ocr_result import OCRResult
from app.repositories.tenant_scoped_repository import TenantScopedRepository
from app.utils.enums import OCRProcessingStatus


class OCRRepository(TenantScopedRepository[OCRResult]):
    def __init__(self, db: Session, tenant_id: UUID) -> None:
        super().__init__(db=db, model=OCRResult, tenant_id=tenant_id)

    def _ensure_document_belongs_to_tenant(self, result: OCRResult) -> None:
        document_exists = (
            self.db.query(CustomerDocument.id)
            .filter(
                CustomerDocument.id == result.document_id,
                CustomerDocument.tenant_id == self.tenant_id,
            )
            .first()
        )
        if document_exists is None:
            raise ValueError(
                "The source document does not belong to the current tenant."
            )

    def create(self, result: OCRResult) -> OCRResult:
        self._ensure_document_belongs_to_tenant(result)
        return super().create(result)

    def update(self, result: OCRResult) -> OCRResult:
        self._ensure_document_belongs_to_tenant(result)
        return super().update(result)

    def get_by_id(self, result_id: UUID) -> OCRResult | None:
        return self.query().filter(OCRResult.id == result_id).first()

    def get_latest_by_document(self, document_id: UUID) -> OCRResult | None:
        return (
            self.query()
            .filter(OCRResult.document_id == document_id)
            .order_by(OCRResult.created_at.desc())
            .first()
        )

    def update_status(
        self,
        result: OCRResult,
        status: OCRProcessingStatus,
        extracted_text: str | None = None,
        error_message: str | None = None,
    ) -> OCRResult:
        if result.tenant_id != self.tenant_id:
            raise ValueError("OCR result tenant does not match repository tenant.")
        self._ensure_document_belongs_to_tenant(result)
        result.status = status
        result.extracted_text = extracted_text
        result.error_message = error_message
        self.db.flush()
        self.db.refresh(result)
        return result
