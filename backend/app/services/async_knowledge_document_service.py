"""Async knowledge-document management."""

from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.models.knowledge_document import KnowledgeDocument
from app.repositories.async_knowledge_document_repository import (
    AsyncKnowledgeDocumentRepository,
)
from app.schemas.knowledge_document import KnowledgeDocumentVersionCreate
from app.services.async_audit_service import AsyncAuditService
from app.services.async_file_service import AsyncFileService, bind_async_tenant
from app.services.async_tenant_access_audit import deny_tenant_access
from app.storages.base_storage import BaseStorage
from app.utils.enums import (
    AuditEventType,
    KnowledgeDocumentCategory,
    KnowledgeDocumentStatus,
)
from app.utils.errors import bad_request


class AsyncKnowledgeDocumentService:
    def __init__(
        self,
        db: AsyncSession,
        file_service: AsyncFileService,
        tenant_id: UUID,
        *,
        actor_user_id: UUID | None = None,
        actor_email: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        storage: BaseStorage | None = None,
    ) -> None:
        if file_service.db is not db or file_service.tenant_id != tenant_id:
            raise ValueError(
                "Knowledge document and file services must share the same "
                "AsyncSession and tenant."
            )
        bind_async_tenant(
            db,
            tenant_id,
            user_id=actor_user_id,
            email=actor_email,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db = db
        self.tenant_id = tenant_id
        self.actor_user_id = actor_user_id
        self.actor_email = actor_email
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.repository = AsyncKnowledgeDocumentRepository(
            db=db,
            tenant_id=tenant_id,
        )
        self.file_service = file_service
        self.audit_service = AsyncAuditService(db)
        self.storage = storage or file_service.storage

    async def _cleanup_uploaded_file(self, storage_path: str | None) -> None:
        if storage_path is None:
            return
        try:
            exists = await run_in_threadpool(self.storage.exists, storage_path)
            if exists:
                await run_in_threadpool(self.storage.delete, storage_path)
        except Exception:
            # Keep the original database/service failure.
            pass

    async def create_document(
        self,
        name: str,
        category: KnowledgeDocumentCategory,
        file: UploadFile,
        uploaded_by: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> KnowledgeDocument:
        name = name.strip()
        if not name:
            raise bad_request("Document name is required.")

        existing_document = await self.repository.get_latest_by_name(name)
        if existing_document is not None:
            raise bad_request(
                f"A knowledge document named '{name}' already exists. "
                "Create a new version instead."
            )

        storage_path: str | None = None
        try:
            stored_file = await self.file_service.upload_file(
                file=file,
                uploaded_by=uploaded_by,
                email=email,
                module="knowledge_base",
                folder="knowledge",
                commit=False,
            )
            storage_path = stored_file.storage_path
            document = KnowledgeDocument(
                tenant_id=self.tenant_id,
                name=name,
                category=category.value,
                file_reference=str(stored_file.id),
                version=1,
                status=KnowledgeDocumentStatus.INACTIVE,
                uploaded_by=uploaded_by,
            )
            await self.repository.create(document)
            await self.audit_service.log_event(
                event_type=AuditEventType.KNOWLEDGE_DOCUMENT_CREATED,
                user_id=uploaded_by,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="knowledge_document",
                resource_id=document.id,
            )
            await self.db.commit()
            await self.db.refresh(document)
            return document
        except Exception:
            await self.db.rollback()
            await self._cleanup_uploaded_file(storage_path)
            raise

    async def create_version(
        self,
        document_id: UUID,
        file: UploadFile,
        uploaded_by: UUID,
        email: str,
        data: KnowledgeDocumentVersionCreate,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> KnowledgeDocument:
        latest_document = await self.repository.get_by_id(document_id)
        if latest_document is None:
            await deny_tenant_access(
                self.db,
                user_id=uploaded_by,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="knowledge_customer",
                resource_id=document_id,
                resource_name="Knowledge Customer",
            )

        name = data.name.strip() if data.name else latest_document.name
        category = (
            data.category.value
            if data.category is not None
            else latest_document.category
        )
        latest_version = await self.repository.get_latest_by_name(name)
        if latest_version is None:
            raise bad_request("Unable to determine the latest document version.")

        next_version = latest_version.version + 1
        storage_path: str | None = None
        try:
            stored_file = await self.file_service.upload_file(
                file=file,
                uploaded_by=uploaded_by,
                email=email,
                module="knowledge_base",
                folder="knowledge",
                commit=False,
            )
            storage_path = stored_file.storage_path
            document = KnowledgeDocument(
                tenant_id=self.tenant_id,
                name=name,
                category=category,
                file_reference=str(stored_file.id),
                version=next_version,
                status=KnowledgeDocumentStatus.INACTIVE,
                uploaded_by=uploaded_by,
            )
            await self.repository.create(document)
            await self.audit_service.log_event(
                event_type=AuditEventType.KNOWLEDGE_DOCUMENT_VERSION_CREATED,
                user_id=uploaded_by,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="knowledge_document",
                resource_id=document.id,
            )
            await self.db.commit()
            await self.db.refresh(document)
            return document
        except Exception:
            await self.db.rollback()
            await self._cleanup_uploaded_file(storage_path)
            raise

    async def get_document(self, document_id: UUID) -> KnowledgeDocument:
        document = await self.repository.get_by_id(document_id)
        if document is None:
            await deny_tenant_access(
                self.db,
                user_id=self.actor_user_id,
                email=self.actor_email,
                ip_address=self.ip_address,
                user_agent=self.user_agent,
                resource_type="knowledge_customer",
                resource_id=document_id,
                resource_name="Knowledge Customer",
            )
        return document

    async def get_documents(self) -> list[KnowledgeDocument]:
        return await self.repository.get_all_ordered()

    async def get_versions(self, document_id: UUID) -> list[KnowledgeDocument]:
        document = await self.repository.get_by_id(document_id)
        if document is None:
            await deny_tenant_access(
                self.db,
                user_id=self.actor_user_id,
                email=self.actor_email,
                ip_address=self.ip_address,
                user_agent=self.user_agent,
                resource_type="knowledge_customer",
                resource_id=document_id,
                resource_name="Knowledge Customer",
            )
        return await self.repository.get_all_versions(document.name)

    async def activate_document(
        self,
        document_id: UUID,
        uploaded_by: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> KnowledgeDocument:
        document = await self.repository.get_by_id(document_id)
        if document is None:
            await deny_tenant_access(
                self.db,
                user_id=self.actor_user_id,
                email=self.actor_email,
                ip_address=self.ip_address,
                user_agent=self.user_agent,
                resource_type="knowledge_customer",
                resource_id=document_id,
                resource_name="Knowledge Customer",
            )
        if document.status == KnowledgeDocumentStatus.ACTIVE:
            raise bad_request("The knowledge document is already active.")

        active_document = await self.repository.get_active_by_name(document.name)
        if active_document is not None:
            raise bad_request(
                "Another version of this document is already active. "
                "Deactivate it before activating this version."
            )

        document.status = KnowledgeDocumentStatus.ACTIVE
        await self.repository.update(document)
        await self.audit_service.log_event(
            event_type=AuditEventType.KNOWLEDGE_DOCUMENT_ACTIVATED,
            user_id=uploaded_by,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="knowledge_document",
            resource_id=document.id,
        )
        await self.db.commit()
        await self.db.refresh(document)
        return document

    async def deactivate_document(
        self,
        document_id: UUID,
        uploaded_by: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> KnowledgeDocument:
        document = await self.repository.get_by_id(document_id)
        if document is None:
            await deny_tenant_access(
                self.db,
                user_id=self.actor_user_id,
                email=self.actor_email,
                ip_address=self.ip_address,
                user_agent=self.user_agent,
                resource_type="knowledge_customer",
                resource_id=document_id,
                resource_name="Knowledge Customer",
            )
        if document.status == KnowledgeDocumentStatus.INACTIVE:
            raise bad_request("The knowledge document is already inactive.")

        document.status = KnowledgeDocumentStatus.INACTIVE
        await self.repository.update(document)
        await self.audit_service.log_event(
            event_type=AuditEventType.KNOWLEDGE_DOCUMENT_DEACTIVATED,
            user_id=uploaded_by,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="knowledge_document",
            resource_id=document.id,
        )
        await self.db.commit()
        await self.db.refresh(document)
        return document
