from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.document_extraction_review_log import (
    DocumentExtractionReviewLog,
)
from app.repositories.document_extraction_review_log_repository import (
    DocumentExtractionReviewLogRepository,
)


class DocumentExtractionReviewLogService:
    def __init__(self, db: Session) -> None:
        self.repository = DocumentExtractionReviewLogRepository(db)

    def log_change(
        self,
        *,
        extraction_id: UUID,
        reviewer_id: UUID,
        field_name: str,
        old_value: object | None,
        new_value: object | None,
    ) -> DocumentExtractionReviewLog:
        return self.repository.create(
            DocumentExtractionReviewLog(
                document_extraction_id=extraction_id,
                reviewer_id=reviewer_id,
                field_name=field_name,
                old_value=self._serialize(old_value),
                new_value=self._serialize(new_value),
                action="UPDATE",
            )
        )

    @staticmethod
    def _serialize(value: object | None) -> str | None:
        if value is None:
            return None

        if isinstance(value, date):
            return value.isoformat()

        return str(value)

    def get_history(
        self,
        extraction_id: UUID,
    ) -> list[DocumentExtractionReviewLog]:
        return self.repository.get_by_extraction(extraction_id)
