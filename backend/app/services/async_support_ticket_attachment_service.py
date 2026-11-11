"""Async support-ticket attachment upload using the existing authorization rules."""

from pathlib import PurePath
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.models.support_ticket import (
    SupportTicketAttachment,
    SupportTicketHistory,
)
from app.models.user import User
from app.repositories.async_support_ticket_repository import (
    AsyncSupportTicketRepository,
)
from app.services.async_file_service import bind_async_tenant
from app.storages.base_storage import BaseStorage
from app.utils.enums import UserRole
from app.utils.errors import bad_request, not_found

_SUPPORT_STAFF_ROLES = {
    UserRole.SUPPORT_AGENT,
    UserRole.ADMINISTRATOR,
    UserRole.ORGANIZATION_ADMIN,
    UserRole.CUSTOMER_SUCCESS_MANAGER,
}


class AsyncSupportTicketAttachmentService:
    """Async attachment path; the legacy synchronous ticket service is unchanged."""

    def __init__(
        self,
        db: AsyncSession,
        actor: User,
        storage: BaseStorage,
    ) -> None:
        bind_async_tenant(db, actor.tenant_id, user_id=actor.id)
        self.db = db
        self.actor = actor
        self.tenant_id = actor.tenant_id
        self.actor_id = actor.id
        self.storage = storage
        role_value = str(getattr(actor.role, "value", actor.role))
        self.is_support_agent = role_value == UserRole.SUPPORT_AGENT.value
        self.is_staff = role_value in {role.value for role in _SUPPORT_STAFF_ROLES}
        self.repository = AsyncSupportTicketRepository(
            db,
            tenant_id=self.tenant_id,
            actor_id=self.actor_id,
            is_support_agent=self.is_support_agent,
            is_staff=self.is_staff,
        )

    async def add_attachment(
        self,
        ticket_id: UUID,
        upload: UploadFile,
    ) -> SupportTicketAttachment:
        if self.storage is None:
            raise RuntimeError("File storage is not configured for support tickets.")

        ticket = await self.repository.get_ticket(ticket_id)
        if ticket is None:
            raise not_found("Support ticket")

        raw_name = (upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
        filename = PurePath(raw_name).name[:255]
        content_type = (upload.content_type or "").strip().lower()
        if not filename or filename in {".", ".."}:
            raise bad_request("A valid attachment filename is required.")
        if content_type not in set(settings.ALLOWED_FILE_TYPES):
            raise bad_request("Attachment content type is not allowed.")
        max_file_size = settings.MAX_FILE_SIZE
        if max_file_size <= 0:
            raise bad_request(
                "Attachment upload is not enabled by server configuration."
            )

        content = await upload.read(max_file_size + 1)
        if not content:
            raise bad_request("Empty attachments are not allowed.")
        if len(content) > max_file_size:
            raise bad_request("Attachment exceeds the configured maximum file size.")

        storage_path: str | None = None
        try:
            storage_path = await run_in_threadpool(
                self.storage.save,
                file_content=content,
                filename=filename,
                folder=f"support-tickets/{ticket.tenant_id}/{ticket.id}",
            )
            attachment = SupportTicketAttachment(
                id=uuid4(),
                tenant_id=ticket.tenant_id,
                ticket_id=ticket.id,
                original_filename=filename,
                storage_path=storage_path,
                content_type=content_type,
                file_size=len(content),
                uploaded_by=self.actor_id,
            )
            self.db.add(attachment)
            self.db.add(
                SupportTicketHistory(
                    tenant_id=ticket.tenant_id,
                    ticket_id=ticket.id,
                    actor_id=self.actor_id,
                    event_type="ATTACHMENT_ADDED",
                    new_value=str(attachment.id),
                    details=filename,
                )
            )

            # Support Agents may manage tickets across tenants only through the
            # explicitly authorized repository path. Bind the write to the
            # selected ticket tenant for the ORM ownership guard.
            previous_tenant = self.db.info.get("tenant_id")
            self.db.info["tenant_id"] = ticket.tenant_id
            try:
                await self.db.commit()
                await self.db.refresh(attachment)
            except Exception:
                await self.db.rollback()
                raise
            finally:
                if previous_tenant is None:
                    self.db.info.pop("tenant_id", None)
                else:
                    self.db.info["tenant_id"] = previous_tenant
            return attachment
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
