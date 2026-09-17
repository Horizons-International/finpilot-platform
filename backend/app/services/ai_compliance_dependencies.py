from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.ai_compliance_service import AIComplianceService


def get_ai_compliance_service(
    db: Session = Depends(get_db),
) -> AIComplianceService:
    return AIComplianceService(db)
