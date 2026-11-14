"""Reusable dependency factories for AsyncSession-backed services.

The synchronous factories in ``app.core.dependencies`` remain available while
routes are migrated incrementally. These factories deliberately share the
request-scoped ``get_async_db`` dependency so services that compose other async
services receive the same AsyncSession and tenant context.
"""

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import get_async_current_user
from app.core.config import settings
from app.core.database import get_async_db
from app.models.user import User
from app.rag.async_retrieval import AsyncRetrievalService
from app.rag.embeddings import EmbeddingService
from app.services.async_aml_rule_service import AsyncAMLRuleService
from app.services.async_compliance_document_service import (
    AsyncComplianceDocumentService,
)
from app.services.async_compliance_service import AsyncComplianceService
from app.services.async_customer_service import AsyncCustomerService
from app.services.async_document_service import AsyncDocumentService
from app.services.async_file_service import AsyncFileService
from app.services.async_knowledge_document_service import (
    AsyncKnowledgeDocumentService,
)
from app.services.async_knowledge_indexing_service import (
    AsyncKnowledgeIndexingService,
)
from app.services.async_transaction_monitoring_service import (
    AsyncTransactionMonitoringService,
)
from app.services.async_verification_service import AsyncVerificationService
from app.storages.base_storage import BaseStorage
from app.storages.local_storage import LocalStorage


def get_async_customer_service(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> AsyncCustomerService:
    return AsyncCustomerService(db=db, tenant_id=current_user.tenant_id)


def get_async_verification_service(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> AsyncVerificationService:
    return AsyncVerificationService(db=db, tenant_id=current_user.tenant_id)


def get_async_compliance_service(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> AsyncComplianceService:
    return AsyncComplianceService(db=db, tenant_id=current_user.tenant_id)


def get_async_aml_rule_service(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> AsyncAMLRuleService:
    return AsyncAMLRuleService(db=db, tenant_id=current_user.tenant_id)


def get_async_transaction_monitoring_service(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> AsyncTransactionMonitoringService:
    return AsyncTransactionMonitoringService(db=db, tenant_id=current_user.tenant_id)


def get_async_storage() -> BaseStorage:
    """Return the storage adapter used by async services.

    Storage operations are synchronous today; async service implementations
    offload blocking filesystem operations with ``run_in_threadpool``.
    """
    return LocalStorage(settings.STORAGE_PATH)


def get_async_file_service(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    storage: BaseStorage = Depends(get_async_storage),
    current_user: User = Depends(get_async_current_user),
) -> AsyncFileService:
    return AsyncFileService(
        db=db,
        storage=storage,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        actor_email=str(current_user.email),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


def get_async_document_service(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    storage: BaseStorage = Depends(get_async_storage),
    current_user: User = Depends(get_async_current_user),
) -> AsyncDocumentService:
    return AsyncDocumentService(
        db=db,
        storage=storage,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        actor_email=str(current_user.email),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


def get_async_knowledge_document_service(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    file_service: AsyncFileService = Depends(get_async_file_service),
    storage: BaseStorage = Depends(get_async_storage),
    current_user: User = Depends(get_async_current_user),
) -> AsyncKnowledgeDocumentService:
    return AsyncKnowledgeDocumentService(
        db=db,
        file_service=file_service,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        actor_email=str(current_user.email),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        storage=storage,
    )


def get_async_knowledge_indexing_service(
    db: AsyncSession = Depends(get_async_db),
    file_service: AsyncFileService = Depends(get_async_file_service),
    current_user: User = Depends(get_async_current_user),
) -> AsyncKnowledgeIndexingService:
    return AsyncKnowledgeIndexingService(
        db=db,
        file_service=file_service,
        embedding_service=EmbeddingService(),
        tenant_id=current_user.tenant_id,
    )


def get_async_retrieval_service(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> AsyncRetrievalService:
    return AsyncRetrievalService(
        db=db,
        tenant_id=current_user.tenant_id,
    )


def get_async_compliance_document_service(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
    file_service: AsyncFileService = Depends(get_async_file_service),
    storage: BaseStorage = Depends(get_async_storage),
) -> AsyncComplianceDocumentService:
    return AsyncComplianceDocumentService(
        db,
        tenant_id=current_user.tenant_id,
        current_user=current_user,
        file_service=file_service,
        storage=storage,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
