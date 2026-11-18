"""Dependency providers for fully async AI assistant request services."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.exceptions import AIConfigurationError
from app.core.async_security import get_async_current_user
from app.core.database import get_async_db
from app.models.user import User
from app.rag.async_retrieval import AsyncRetrievalService
from app.services.async_ai_analytics_assistant_service import (
    AsyncAIAnalyticsAssistantService,
)
from app.services.async_ai_compliance_service import AsyncAIComplianceService
from app.services.async_regulatory_assistant_service import (
    AsyncRegulatoryAssistantService,
)


def get_optional_async_retrieval_service(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> AsyncRetrievalService | None:
    try:
        return AsyncRetrievalService(db, tenant_id=current_user.tenant_id)
    except AIConfigurationError:
        # Analytics RAG enrichment is optional; compliance/regulatory services
        # report a missing retrieval configuration at the service boundary.
        return None


def get_async_ai_compliance_service(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
    retrieval_service: AsyncRetrievalService | None = Depends(
        get_optional_async_retrieval_service
    ),
) -> AsyncAIComplianceService:
    return AsyncAIComplianceService(
        db,
        tenant_id=current_user.tenant_id,
        retrieval_service=retrieval_service,
    )


def get_async_ai_analytics_assistant_service(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
    retrieval_service: AsyncRetrievalService | None = Depends(
        get_optional_async_retrieval_service
    ),
) -> AsyncAIAnalyticsAssistantService:
    return AsyncAIAnalyticsAssistantService(
        db,
        tenant_id=current_user.tenant_id,
        retrieval_service=retrieval_service,
    )


def get_async_regulatory_assistant_service(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
    retrieval_service: AsyncRetrievalService | None = Depends(
        get_optional_async_retrieval_service
    ),
) -> AsyncRegulatoryAssistantService:
    return AsyncRegulatoryAssistantService(
        db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        retrieval_service=retrieval_service,
    )
