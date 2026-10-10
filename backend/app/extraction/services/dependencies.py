from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.extraction.providers.factory import get_extraction_provider
from app.extraction.services.extraction_service import DocumentExtractionService
from app.models.user import User


def get_document_extraction_service(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentExtractionService:
    return DocumentExtractionService(
        db=db,
        provider=get_extraction_provider(),
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
