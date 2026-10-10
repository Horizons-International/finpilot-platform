from uuid import UUID

from sqlalchemy.orm import Session

from app.models.document_extraction import DocumentExtraction
from app.repositories.tenant_scoped_repository import (
    TenantScopedRepository,
)


class DocumentExtractionRepository(TenantScopedRepository[DocumentExtraction]):
    def __init__(
        self,
        db: Session,
        tenant_id: UUID,
    ) -> None:
        super().__init__(
            db=db,
            model=DocumentExtraction,
            tenant_id=tenant_id,
        )

    def get_latest_by_document(
        self,
        document_id: UUID,
    ) -> DocumentExtraction | None:
        return (
            self.query()
            .filter(
                DocumentExtraction.document_id == document_id,
            )
            .order_by(
                DocumentExtraction.created_at.desc(),
            )
            .first()
        )

    def get_by_ocr_result(
        self,
        ocr_result_id: UUID,
    ) -> DocumentExtraction | None:
        return (
            self.query()
            .filter(
                DocumentExtraction.ocr_result_id == ocr_result_id,
            )
            .first()
        )
