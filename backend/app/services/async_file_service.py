"""Async file workflows using AsyncSession and async repositories."""

from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.models.file import File
from app.repositories.async_file_repository import AsyncFileRepository
from app.services.async_audit_service import AsyncAuditService
from app.services.async_subscription_capacity import ensure_subscription_capacity
from app.services.async_tenant_access_audit import deny_tenant_access
from app.storages.base_storage import BaseStorage
from app.utils.enums import AuditEventType
from app.utils.errors import bad_request, not_found
from app.utils.files import get_filename


def bind_async_tenant(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    user_id: UUID | None = None,
    email: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Bind trusted request context to an async session, rejecting tenant changes."""
    active_tenant = db.info.get("tenant_id")
    if active_tenant is not None and active_tenant != tenant_id:
        raise ValueError("The async session is already bound to another tenant.")
    db.info["tenant_id"] = tenant_id
    if user_id is not None:
        db.info["tenant_user_id"] = user_id
    if email is not None:
        db.info["tenant_user_email"] = email
    if ip_address is not None:
        db.info["tenant_ip_address"] = ip_address
    if user_agent is not None:
        db.info["tenant_user_agent"] = user_agent


class AsyncFileService:
    """Tenant-scoped file persistence and storage operations."""

    def __init__(
        self,
        db: AsyncSession,
        storage: BaseStorage,
        *,
        tenant_id: UUID,
        actor_user_id: UUID | None = None,
        actor_email: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
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
        self.repository = AsyncFileRepository(db, tenant_id)
        self.audit_service = AsyncAuditService(db)
        self.storage = storage

    async def upload_file(
        self,
        file: UploadFile,
        uploaded_by: UUID,
        email: str,
        module: str,
        folder: str,
        commit: bool = True,
        allowed_file_types: set[str] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> File:
        if not file.filename:
            raise bad_request("Filename is required.")
        if file.content_type is None:
            raise bad_request("File content type is required.")

        allowed_types = (
            allowed_file_types
            if allowed_file_types is not None
            else set(settings.ALLOWED_FILE_TYPES)
        )
        if file.content_type not in allowed_types:
            raise bad_request("File type is not supported.")

        file_content = await file.read()
        if len(file_content) > settings.MAX_FILE_SIZE:
            raise bad_request("File size exceeds the maximum allowed size.")

        await ensure_subscription_capacity(
            self.db,
            self.tenant_id,
            metric="storage_bytes",
            additional=len(file_content),
        )

        storage_path: str | None = None
        try:
            storage_path = await run_in_threadpool(
                self.storage.save,
                file_content=file_content,
                filename=file.filename,
                folder=f"{module}/{folder}",
            )
            file_record = File(
                tenant_id=self.tenant_id,
                original_filename=file.filename,
                stored_filename=get_filename(storage_path),
                storage_path=storage_path,
                folder=folder,
                module=module,
                content_type=file.content_type,
                file_size=len(file_content),
                uploaded_by=uploaded_by,
            )
            await self.repository.create(file_record)

            await self.audit_service.log_event(
                event_type=AuditEventType.FILE_UPLOAD,
                user_id=uploaded_by,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="file",
                resource_id=file_record.id,
            )
            if commit:
                await self.db.commit()
                await self.db.refresh(file_record)
            return file_record
        except Exception:
            await self.db.rollback()
            if storage_path is not None:
                try:
                    exists = await run_in_threadpool(self.storage.exists, storage_path)
                    if exists:
                        await run_in_threadpool(self.storage.delete, storage_path)
                except Exception:
                    pass
            raise

    async def read_file(self, file_id: UUID) -> tuple[bytes, str, str]:
        file_record = await self.repository.get_by_id(file_id)
        if file_record is None:
            await deny_tenant_access(
                self.db,
                user_id=self.actor_user_id,
                email=self.actor_email,
                ip_address=self.ip_address,
                user_agent=self.user_agent,
                resource_type="file",
                resource_id=file_id,
                resource_name="File",
            )

        exists = await run_in_threadpool(self.storage.exists, file_record.storage_path)
        if not exists:
            raise not_found("Stored file")
        content = await run_in_threadpool(self.storage.read, file_record.storage_path)
        return content, file_record.original_filename, file_record.content_type

    async def download_file(
        self,
        file_id: UUID,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[bytes, str, str]:
        result = await self.read_file(file_id)
        try:
            await self.audit_service.log_event(
                event_type=AuditEventType.FILE_DOWNLOAD,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="file",
                resource_id=file_id,
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return result

    async def delete_file(
        self,
        file_id: UUID,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        file_record = await self.repository.get_by_id(file_id)
        if file_record is None:
            await deny_tenant_access(
                self.db,
                user_id=self.actor_user_id,
                email=self.actor_email,
                ip_address=self.ip_address,
                user_agent=self.user_agent,
                resource_type="file",
                resource_id=file_id,
                resource_name="File",
            )

        storage_path = file_record.storage_path
        try:
            await run_in_threadpool(self.storage.delete, storage_path)
            await self.repository.delete(file_record)
            await self.audit_service.log_event(
                event_type=AuditEventType.FILE_DELETE,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="file",
                resource_id=file_id,
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
