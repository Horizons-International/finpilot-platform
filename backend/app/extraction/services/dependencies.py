from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.extraction.providers.factory import get_extraction_provider
from app.extraction.services.extraction_service import DocumentExtractionService


def get_document_extraction_service(
    db: Session = Depends(get_db),
) -> DocumentExtractionService:
    return DocumentExtractionService(
        db=db,
        provider=get_extraction_provider(),
    )
