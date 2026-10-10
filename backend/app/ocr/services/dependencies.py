from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.ocr.providers.factory import get_ocr_provider
from app.ocr.services.ocr_service import OCRService


def get_ocr_service(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OCRService:
    return OCRService(
        db=db,
        provider=get_ocr_provider(),
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
