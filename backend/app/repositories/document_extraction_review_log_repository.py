from uuid import UUID

from sqlalchemy.orm import Session

from app.models.document_extraction_review_log import (
    DocumentExtractionReviewLog,
)
from app.repositories.base_repository import BaseRepository


class DocumentExtractionReviewLogRepository(
    BaseRepository[DocumentExtractionReviewLog]
):
    def __init__(self, db: Session) -> None:
        super().__init__(
            db,
            DocumentExtractionReviewLog,
        )

    def get_by_extraction(
        self,
        extraction_id: UUID,
    ) -> list[DocumentExtractionReviewLog]:
        return (
            self.db.query(DocumentExtractionReviewLog)
            .filter(
                DocumentExtractionReviewLog.document_extraction_id == extraction_id,
            )
            .order_by(
                DocumentExtractionReviewLog.created_at.asc(),
            )
            .all()
        )
