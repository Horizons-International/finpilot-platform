from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.document_review_service import DocumentReviewService


def get_document_review_service(
    db: Session = Depends(get_db),
) -> DocumentReviewService:
    return DocumentReviewService(db)
