from uuid import UUID

from sqlalchemy.orm import Session

from app.models.document_extraction import DocumentExtraction
from app.repositories.base_repository import BaseRepository


class DocumentExtractionRepository(BaseRepository[DocumentExtraction]):
    def __init__(self, db: Session) -> None:
        super().__init__(
            db,
            DocumentExtraction,
        )

    def get_latest_by_document(
        self,
        document_id: UUID,
    ) -> DocumentExtraction | None:
        return (
            self.db.query(DocumentExtraction)
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
            self.db.query(DocumentExtraction)
            .filter(
                DocumentExtraction.ocr_result_id == ocr_result_id,
            )
            .first()
        )
