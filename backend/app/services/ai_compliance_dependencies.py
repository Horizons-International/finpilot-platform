from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.rag.retrieval import RetrievalService
from app.services.ai_compliance_service import (
    AIComplianceService,
)


def get_ai_compliance_service(
    db: Session = Depends(get_db),
) -> AIComplianceService:
    retrieval_service = RetrievalService(db)

    return AIComplianceService(
        db,
        retrieval_service=retrieval_service,
    )
