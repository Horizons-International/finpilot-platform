from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.ocr.providers.factory import get_ocr_provider
from app.ocr.services.ocr_service import OCRService


def get_ocr_service(
    db: Session = Depends(get_db),
) -> OCRService:
    return OCRService(
        db=db,
        provider=get_ocr_provider(),
    )
