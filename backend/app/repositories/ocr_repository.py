from uuid import UUID

from sqlalchemy.orm import Session

from app.models.ocr_result import OCRResult
from app.utils.enums import OCRProcessingStatus


class OCRRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, result: OCRResult) -> OCRResult:
        self.db.add(result)
        self.db.flush()
        self.db.refresh(result)

        return result

    def get_by_id(self, result_id: UUID) -> OCRResult | None:
        return self.db.query(OCRResult).filter(OCRResult.id == result_id).first()

    def get_latest_by_document(
        self,
        document_id: UUID,
    ) -> OCRResult | None:
        return (
            self.db.query(OCRResult)
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
        result.status = status
        result.extracted_text = extracted_text
        result.error_message = error_message

        self.db.flush()
        self.db.refresh(result)

        return result
