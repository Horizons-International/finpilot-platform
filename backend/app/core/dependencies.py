"""Dependencies for the intentionally synchronous application services.

Most request-facing database services now use native AsyncSession dependencies
in their routers. Keep only the providers that still back deliberately
synchronous workflows or synchronous third-party integrations.
"""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.ai.exceptions import AIConfigurationError
from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.rag.retrieval import RetrievalService
from app.services.ai_analytics_assistant_service import (
    AIAnalyticsAssistantService,
)
from app.services.ai_compliance_service import AIComplianceService
from app.services.regulatory_assistant_service import RegulatoryAssistantService
from app.services.report_export_service import ReportExportService
from app.storages.base_storage import BaseStorage
from app.storages.local_storage import LocalStorage


def get_storage() -> BaseStorage:
    """Provide the configured synchronous storage adapter.

    Storage remains synchronous because some request handlers and the report
    export worker use the existing BaseStorage contract. Async callers should
    offload blocking storage operations rather than call them on the event loop.
    """
    return LocalStorage(settings.STORAGE_PATH)


def get_optional_retrieval_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RetrievalService | None:
    """Build optional synchronous retrieval for the sync AI assistant routes."""
    try:
        return RetrievalService(
            db,
            tenant_id=current_user.tenant_id,
        )
    except AIConfigurationError:
        return None


def get_ai_analytics_assistant_service(
    db: Session = Depends(get_db),
    retrieval_service: RetrievalService | None = Depends(
        get_optional_retrieval_service,
    ),
    current_user: User = Depends(get_current_user),
) -> AIAnalyticsAssistantService:
    return AIAnalyticsAssistantService(
        db=db,
        retrieval_service=retrieval_service,
        tenant_id=current_user.tenant_id,
    )


def get_report_export_service(
    db: Session = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
    current_user: User = Depends(get_current_user),
) -> ReportExportService:
    """Keep sync export creation/download paths on their existing services."""
    return ReportExportService(
        db=db,
        storage=storage,
        tenant_id=current_user.tenant_id,
    )


def get_regulatory_assistant_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RegulatoryAssistantService:
    return RegulatoryAssistantService(
        db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        retrieval_service_factory=lambda: RetrievalService(
            db,
            tenant_id=current_user.tenant_id,
        ),
    )


def get_ai_compliance_service(
    db: Session = Depends(get_db),
    retrieval_service: RetrievalService | None = Depends(
        get_optional_retrieval_service,
    ),
    current_user: User = Depends(get_current_user),
) -> AIComplianceService:
    return AIComplianceService(
        db,
        retrieval_service=retrieval_service,
        tenant_id=current_user.tenant_id,
    )
